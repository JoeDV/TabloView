import unittest
from unittest import mock

from app import childproc


class ChildProcessTests(unittest.TestCase):
    """FFmpeg ends with TabloView: a job object on Windows (checked by killing a parent for real),
    PR_SET_PDEATHSIG on Linux, set at launch alongside any other launch step."""

    def test_linux_runs_the_other_launch_step_then_ties_ffmpeg_to_tabloview(self):
        calls = []
        with mock.patch.object(childproc.sys, "platform", "linux"), \
             mock.patch.object(childproc, "_die_with_parent", new=lambda: calls.append("die with parent")):
            kw = childproc.popen_kwargs(lambda: calls.append("lower priority"))
            kw["preexec_fn"]()
        self.assertEqual(calls, ["lower priority", "die with parent"])

    def test_elsewhere_only_the_other_launch_step(self):
        step = mock.Mock()
        with mock.patch.object(childproc.sys, "platform", "darwin"):
            self.assertEqual(childproc.popen_kwargs(step), {"preexec_fn": step})
            self.assertEqual(childproc.popen_kwargs(), {})

    def test_tying_never_raises(self):
        with mock.patch.object(childproc.sys, "platform", "win32"):
            childproc.tie_to_app(mock.Mock(_handle=0))  # an invalid process: logged, not raised


if __name__ == "__main__":
    unittest.main()
