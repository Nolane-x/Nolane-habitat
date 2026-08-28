from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from habitat.truth.authority import AuthorityClass
from habitat.truth.claims import make_truth_claim


class TruthProjectionTests(unittest.TestCase):
    def _claim(
        self,
        *,
        subject: str = "symbol:demo.f",
        predicate: str = "semantic:definition",
        value=None,
        authority: AuthorityClass = AuthorityClass.PARSER_DERIVED,
        revision: str = "rev-1",
        producer: str = "test-provider",
        path: str | None = None,
        source_digest: str | None = None,
    ):
        return make_truth_claim(
            subject=subject,
            predicate=predicate,
            value={"value": value},
            authority_class=authority,
            revision=revision,
            producer=producer,
            path=path,
            source_digest=source_digest,
        )

    def test_revision_mismatch_is_stale(self):
        from habitat.truth.projection import StaleClaimRecord, claim_staleness

        claim = self._claim(revision="rev-old", value="old")
        stale = claim_staleness(claim, current_revision="rev-new", current_digests={})

        self.assertIsInstance(stale, StaleClaimRecord)
        self.assertEqual(stale.claim_id, claim.id)
        self.assertEqual(stale.reasons, ("revision-mismatch",))
        self.assertEqual(stale.current_revision, "rev-new")
        with self.assertRaises(FrozenInstanceError):
            stale.status = "current"

    def test_digest_mismatch_and_unavailable_binding_fail_closed(self):
        from habitat.truth.projection import claim_staleness

        claim = self._claim(
            value="bound",
            path="demo.py",
            source_digest="a" * 64,
        )
        mismatch = claim_staleness(
            claim,
            current_revision="rev-1",
            current_digests={"demo.py": "b" * 64},
        )
        missing = claim_staleness(
            claim,
            current_revision="rev-1",
            current_digests={},
        )
        unavailable = claim_staleness(
            claim,
            current_revision="rev-1",
            current_digests={"demo.py": None},
        )

        self.assertEqual(mismatch.reasons, ("source-digest-mismatch",))
        self.assertEqual(mismatch.current_source_digest, "b" * 64)
        self.assertEqual(missing.reasons, ("source-digest-unavailable",))
        self.assertIsNone(missing.current_source_digest)
        self.assertEqual(unavailable.reasons, ("source-digest-unavailable",))

    def test_stale_historical_claim_does_not_create_contradiction(self):
        from habitat.truth.projection import project_truth

        historical = self._claim(value="old", revision="rev-1", producer="old")
        current = self._claim(value="new", revision="rev-2", producer="current")
        projection = project_truth(
            [historical, current],
            current_revision="rev-2",
            current_digests={},
        )

        self.assertEqual(projection["stale_count"], 1)
        self.assertEqual(projection["stale_claims"][0].claim_id, historical.id)
        self.assertEqual(projection["contradiction_count"], 0)
        self.assertEqual(projection["contradictions"], ())

    def test_current_unequal_values_create_one_unresolved_contradiction(self):
        from habitat.truth.projection import TruthContradictionRecord, project_truth

        left = self._claim(value="left", producer="parser-a")
        right = self._claim(
            value="right",
            producer="model-b",
            authority=AuthorityClass.MODEL_INFERRED,
        )
        projection = project_truth(
            [left, right],
            current_revision="rev-1",
            current_digests={},
        )

        self.assertEqual(projection["contradiction_count"], 1)
        contradiction = projection["contradictions"][0]
        self.assertIsInstance(contradiction, TruthContradictionRecord)
        self.assertEqual(contradiction.claim_ids, tuple(sorted((left.id, right.id))))
        self.assertEqual(contradiction.subject, left.subject)
        self.assertEqual(contradiction.predicate, left.predicate)
        self.assertEqual(contradiction.revision, "rev-1")
        self.assertEqual(contradiction.status, "unresolved")
        self.assertEqual(
            set(contradiction.authority_classes),
            {AuthorityClass.PARSER_DERIVED, AuthorityClass.MODEL_INFERRED},
        )
        self.assertFalse(hasattr(contradiction, "winner_claim_id"))
        with self.assertRaises(FrozenInstanceError):
            contradiction.status = "resolved"

    def test_input_order_does_not_change_projection_or_record_ids(self):
        from habitat.truth.projection import project_truth

        claims = [
            self._claim(value="a", producer="one"),
            self._claim(value="b", producer="two"),
            self._claim(
                subject="file:other.py",
                predicate="source_snapshot",
                value="old",
                revision="rev-old",
                producer="three",
            ),
        ]
        forward = project_truth(claims, current_revision="rev-1", current_digests={})
        reverse = project_truth(list(reversed(claims)), current_revision="rev-1", current_digests={})

        self.assertEqual(forward, reverse)

    def test_weaker_claim_plurality_never_upgrades_authority(self):
        from habitat.truth.projection import project_truth

        claims = [
            self._claim(
                value="model-consensus",
                authority=AuthorityClass.MODEL_INFERRED,
                producer=f"model-{index}",
            )
            for index in range(3)
        ]
        claims.append(self._claim(value="parser-value", producer="parser"))
        projection = project_truth(claims, current_revision="rev-1", current_digests={})

        contradiction = projection["contradictions"][0]
        self.assertEqual(
            set(contradiction.authority_classes),
            {AuthorityClass.MODEL_INFERRED, AuthorityClass.PARSER_DERIVED},
        )
        self.assertNotIn(AuthorityClass.SOURCE_EXACT, contradiction.authority_classes)
        self.assertEqual(
            [claim.authority_class for claim in projection["claims"]].count(AuthorityClass.MODEL_INFERRED),
            3,
        )

    def test_bounds_and_truncation_are_deterministic(self):
        from habitat.truth.projection import project_truth

        claims = [
            self._claim(subject=f"object:{index}", predicate="state", value=index, producer=f"p-{index}")
            for index in range(5)
        ]
        forward = project_truth(
            claims,
            current_revision="rev-1",
            current_digests={},
            max_claims=3,
        )
        reverse = project_truth(
            list(reversed(claims)),
            current_revision="rev-1",
            current_digests={},
            max_claims=3,
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(forward["input_claim_count"], 5)
        self.assertEqual(forward["claim_count"], 3)
        self.assertTrue(forward["truncated"])
        self.assertEqual(len(forward["claims"]), 3)
        with self.assertRaises(ValueError):
            project_truth(claims, current_revision="rev-1", current_digests={}, max_claims=0)
        with self.assertRaises(ValueError):
            project_truth(claims, current_revision="rev-1", current_digests={}, max_claims=True)


if __name__ == "__main__":
    unittest.main()
