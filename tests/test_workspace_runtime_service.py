from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import habitat.services.runtime as runtime_service_module
from habitat.services import RuntimeService
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


class RuntimeServiceRoutingTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "habitat")

    def test_public_runtime_methods_route_once_through_runtime_service(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            calls: list[tuple] = []
            try:
                def fake_ingest(service, signal, records, *, agent_id=None, episode_id=None):
                    calls.append(("runtime_ingest", service, signal, tuple(records), agent_id, episode_id))
                    return {"sentinel": "ingest"}

                def fake_timeline(service, *, trace_id=None, agent_id=None, limit=200):
                    calls.append(("runtime_timeline", service, trace_id, agent_id, limit))
                    return {"sentinel": "timeline"}

                def fake_topology(service, *, agent_id=None, limit=500):
                    calls.append(("runtime_topology", service, agent_id, limit))
                    return {"sentinel": "topology"}

                with (
                    patch.object(RuntimeService, "runtime_ingest", new=fake_ingest, create=True),
                    patch.object(RuntimeService, "runtime_timeline", new=fake_timeline, create=True),
                    patch.object(RuntimeService, "runtime_topology", new=fake_topology, create=True),
                ):
                    self.assertEqual(
                        ws.runtime_ingest(
                            "opentelemetry",
                            [],
                            agent_id="agent:1",
                            episode_id="episode:1",
                        ),
                        {"sentinel": "ingest"},
                    )
                    self.assertEqual(
                        ws.runtime_timeline(trace_id="trace:1", agent_id="agent:2", limit=17),
                        {"sentinel": "timeline"},
                    )
                    self.assertEqual(
                        ws.runtime_topology(agent_id="agent:3", limit=19),
                        {"sentinel": "topology"},
                    )

                service = ws._runtime_operations()
                self.assertEqual(
                    calls,
                    [
                        ("runtime_ingest", service, "opentelemetry", (), "agent:1", "episode:1"),
                        ("runtime_timeline", service, "trace:1", "agent:2", 17),
                        ("runtime_topology", service, "agent:3", 19),
                    ],
                )
            finally:
                ws.close()

    def test_runtime_service_calls_preserved_core_without_public_recursion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            service = ws._runtime_operations()
            try:
                core = runtime_service_module._CoreHabitatWorkspace
                with (
                    patch.object(core, "runtime_ingest", return_value={"sentinel": "core-ingest"}) as core_ingest,
                    patch.object(core, "runtime_timeline", return_value={"sentinel": "core-timeline"}) as core_timeline,
                    patch.object(core, "runtime_topology", return_value={"sentinel": "core-topology"}) as core_topology,
                ):
                    self.assertEqual(
                        service.runtime_ingest(
                            "dap",
                            [],
                            agent_id="agent:4",
                            episode_id="episode:4",
                        ),
                        {"sentinel": "core-ingest"},
                    )
                    self.assertEqual(
                        service.runtime_timeline(trace_id="trace:4", agent_id="agent:5", limit=23),
                        {"sentinel": "core-timeline"},
                    )
                    self.assertEqual(
                        service.runtime_topology(agent_id="agent:6", limit=29),
                        {"sentinel": "core-topology"},
                    )

                core_ingest.assert_called_once_with(
                    ws,
                    "dap",
                    [],
                    agent_id="agent:4",
                    episode_id="episode:4",
                )
                core_timeline.assert_called_once_with(
                    ws,
                    trace_id="trace:4",
                    agent_id="agent:5",
                    limit=23,
                )
                core_topology.assert_called_once_with(ws, agent_id="agent:6", limit=29)
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()
