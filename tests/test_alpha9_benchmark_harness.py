import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

from benchmarks.agent_ab_harness import command_args

class Alpha9ABHarnessTests(unittest.TestCase):
    def test_command_args_preserves_windows_paths(self):
        command = r"C:\Users\admin\Python\python.exe C:\Users\admin\agent.py" if os.name == "nt" else "python agent.py"
        expected = [r"C:\Users\admin\Python\python.exe", r"C:\Users\admin\agent.py"] if os.name == "nt" else ["python", "agent.py"]
        self.assertEqual(command_args(command), expected)

    def test_harness_runs_paired_arms_without_inventing_model_results(self):
        base=Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); repo=td/'repo'; repo.mkdir(); (repo/'a.py').write_text('x=1\n')
            suite=td/'suite.json'; suite.write_text(json.dumps({'tasks':[{'id':'t1','repo':str(repo),'prompt':'inspect x'}]}))
            agent=td/'agent.py'; agent.write_text('''import json,sys\np=json.load(sys.stdin)\nprint(json.dumps({"task_id":p["task_id"],"success":True,"tool_calls":1,"input_tokens":10,"output_tokens":5,"wall_ms":3}))\n''')
            out=td/'out.json'; cmd=f'{sys.executable} {agent}'
            subprocess.run([sys.executable,str(base/'benchmarks'/'agent_ab_harness.py'),'--suite',str(suite),'--baseline-cmd',cmd,'--habitat-cmd',cmd,'--repetitions','2','--out',str(out)],check=True,capture_output=True,text=True)
            report=json.loads(out.read_text()); self.assertEqual(len(report['runs']),4)
            self.assertEqual({r['arm'] for r in report['runs']},{'filesystem','habitat'})
            self.assertTrue(report['same_model_required']); self.assertIn('only',report['claim_boundary'])
