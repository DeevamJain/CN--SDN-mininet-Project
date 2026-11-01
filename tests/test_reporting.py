import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
from jackfruit.analyze import analyze


class ReportingTests(unittest.TestCase):
    def test_cohorts_use_first_send_and_keep_missing_cohorts_empty(self):
        with tempfile.TemporaryDirectory() as name:
            run = Path(name)/'measured-fixture'
            run.mkdir()
            meta = dict(valid=True, mode='dynamic', scenario='loss', seed=1,
                        fault_wall=102, controller=dict(switch_completed_wall=104))
            data = dict(transfer='fixture', packets=3, sent_datagrams=4,
                acked=3, failed=0, initial_sent=3, unsent=0, retransmissions=1,
                first_attempt_timeout_ratio=1/3, final_unacked_ratio=0, goodput_bps=123,
                duration_s=6, rtt_p50_ms=1, rtt_p95_ms=2,
                first_retransmitted_ack_after_detection_s=.1, start_wall=100,
                packet_records=[dict(first_sent_s=t, first_timeout=lost)
                                for t,lost in [(1,False),(3,True),(5,False)]])
            (run/'experiment.json').write_text(json.dumps(meta))
            (run/'client1.json').write_text(json.dumps(data))
            (run/'receiver.json').write_text(json.dumps(dict(sessions=[dict(transfer='fixture',
                unique=3, missing=0, duplicates=0, received_datagrams=3)])))
            with contextlib.redirect_stdout(io.StringIO()):
                row = analyze(name)[0]
            self.assertEqual(row['before_fault_packets'], 1)
            self.assertEqual(row['during_recovery_timeout_ratio'], 1)
            self.assertEqual(row['after_recovery_timeout_ratio'], 0)

    def test_invalid_runs_cannot_create_measured_report(self):
        with tempfile.TemporaryDirectory() as name:
            run = Path(name)/'failed'
            run.mkdir()
            (run/'experiment.json').write_text(json.dumps(dict(valid=False)))
            with self.assertRaises(ValueError):
                analyze(name)
            self.assertFalse((Path(name)/'REPORT.md').exists())
