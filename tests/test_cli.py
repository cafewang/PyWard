import os
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# The script to be tested, which should contain the corrected main(),
# analyze_file(), and ArgumentParser1 classes.
from pyward.cli import main

FILE_CONTENT = "import os\n\nprint('Hello')\n"


@pytest.fixture
def temp_python_file():
    """Creates a temporary python file for testing."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.py")
    with open(path, "w") as f:
        f.write(FILE_CONTENT)
    yield path
    os.remove(path)
    os.rmdir(d)


@pytest.fixture
def mock_analyze_file():
    """Mocks the analyze_file function within the cli module."""
    with patch("pyward.cli.analyze_file") as m:
        yield m


@pytest.fixture
def mock_fix_file():
    """Mocks the fix_file function within the cli module."""
    with patch("pyward.cli.fix_file") as m:
        yield m


class TestCLIMain:
    def test_no_issues(self, temp_python_file, mock_analyze_file):
        """Tests the CLI output when no issues are found."""
        mock_analyze_file.return_value = []
        with patch.object(sys, "argv", ["pyward", temp_python_file]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        mock_analyze_file.assert_called_once_with(
            FILE_CONTENT, run_optimization=True, run_security=True, skip_list=[]
        )
        assert "✅ No issues found" in out.getvalue()
        assert e.value.code == 0

    def test_with_issues(self, temp_python_file, mock_analyze_file):
        """Tests the CLI output when issues are returned."""
        mock_analyze_file.return_value = ["Line 1: Some issue", "Line 3: Another issue"]
        with patch.object(sys, "argv", ["pyward", temp_python_file]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        output = out.getvalue()
        assert "❌ Found 2 issue(s)" in output
        assert "1. Line 1: Some issue" in output
        assert "2. Line 3: Another issue" in output
        assert e.value.code == 1

    @pytest.mark.parametrize(
        "flags,opt,sec",
        [
            ([], True, True),
            (["-o"], True, False),
            (["-s"], False, True),
        ],
    )
    def test_flag_combinations(
        self, temp_python_file, mock_analyze_file, flags, opt, sec
    ):
        """Tests the logic for -o and -s flags."""
        mock_analyze_file.return_value = []
        argv = ["pyward"] + flags + [temp_python_file]
        with patch.object(sys, "argv", argv), patch("sys.stdout", new=StringIO()):
            with pytest.raises(SystemExit):
                main()

        mock_analyze_file.assert_called_once_with(
            FILE_CONTENT, run_optimization=opt, run_security=sec, skip_list=[]
        )

    def test_skip_checks_argument(self, temp_python_file, mock_analyze_file):
        """Verifies that the --skip-checks argument is parsed correctly."""
        mock_analyze_file.return_value = []
        skip_arg = "unused_import,no_exec"
        expected_list = ["check_unused_import", "check_no_exec"]
        argv = ["pyward", "--skip-checks", skip_arg, temp_python_file]

        with patch.object(sys, "argv", argv), patch("sys.stdout", new=StringIO()):
            with pytest.raises(SystemExit):
                main()

        mock_analyze_file.assert_called_once_with(
            FILE_CONTENT,
            run_optimization=True,
            run_security=True,
            skip_list=expected_list,
        )

    @pytest.mark.parametrize("vf", ["-v", "--verbose"])
    def test_verbose_flag_no_issues(self, temp_python_file, mock_analyze_file, vf):
        """Tests verbose output when there are no issues."""
        mock_analyze_file.return_value = []
        with patch.object(sys, "argv", ["pyward", vf, temp_python_file]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        assert "✅ No issues found in" in out.getvalue()
        assert "(verbose)" in out.getvalue()
        assert e.value.code == 0

    def test_no_filepath(self):
        """Tests that the program exits correctly if no filepath is given."""
        with patch.object(sys, "argv", ["pyward"]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        assert e.value.code == 1
        output = out.getvalue()
        assert "usage: pyward" in output
        assert "the following arguments are required: filepath" in output

    def test_help(self):
        """Tests the -h/--help message."""
        with patch.object(sys, "argv", ["pyward", "-h"]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        help_text = out.getvalue()
        assert "PyWard: CLI linter for Python" in help_text
        assert e.value.code == 0

    def test_mutually_exclusive_error(self, temp_python_file):
        """Tests that -o and -s flags cannot be used together."""
        with patch.object(sys, "argv", ["pyward", "-o", "-s", temp_python_file]), patch(
            "sys.stderr", new=StringIO()
        ) as err:
            with pytest.raises(SystemExit) as e:
                main()

        assert e.value.code == 2
        assert "not allowed with" in err.getvalue()

    def test_file_not_found(self):
        """Tests the error handling for a file that does not exist."""
        with patch.object(sys, "argv", ["pyward", "nonexistent.py"]), patch(
            "sys.stderr", new=StringIO()
        ) as err:
            with pytest.raises(SystemExit) as e:
                main()

        assert "Error: File 'nonexistent.py' not found" in err.getvalue()
        assert e.value.code == 1

    def test_general_exception(self, temp_python_file, mock_analyze_file):
        """Tests the general exception handler during analysis."""
        mock_analyze_file.side_effect = Exception("boom")
        with patch.object(sys, "argv", ["pyward", temp_python_file]), patch(
            "sys.stderr", new=StringIO()
        ) as err:
            with pytest.raises(SystemExit) as e:
                main()

        assert f"Error analyzing {temp_python_file}: boom" in err.getvalue()
        assert e.value.code == 1

    @pytest.mark.parametrize("fix_flag", ["-f", "--fix"])
    def test_fix_flag_no_issues(
        self, temp_python_file, mock_analyze_file, mock_fix_file, fix_flag
    ):
        """Tests output when --fix is used but no fixes are applied."""
        mock_analyze_file.return_value = []
        mock_fix_file.return_value = (False, "", [])
        with patch.object(sys, "argv", ["pyward", fix_flag, temp_python_file]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        assert "✅ No issues found in" in out.getvalue()
        assert e.value.code == 0

    @pytest.mark.parametrize("fix_flag", ["-f", "--fix"])
    def test_fix_flag_file_changed(
        self, temp_python_file, mock_analyze_file, mock_fix_file, fix_flag
    ):
        """Tests output when --fix causes changes to the file."""
        mock_analyze_file.return_value = []
        fix_msgs = ["fix message"]
        mock_fix_file.return_value = (True, "new content", fix_msgs)
        with patch.object(sys, "argv", ["pyward", fix_flag, temp_python_file]), patch(
            "sys.stdout", new=StringIO()
        ) as out:
            with pytest.raises(SystemExit) as e:
                main()

        assert (
            f"🔧 Applied {len(fix_msgs)} fix(es) to {temp_python_file}"
            in out.getvalue()
        )
        assert fix_msgs[0] in out.getvalue()
        assert e.value.code == 0

    @pytest.mark.parametrize("fix_flag", ["-f", "--fix"])
    def test_fix_flag_with_fix_file_throws(
        self, temp_python_file, mock_analyze_file, mock_fix_file, fix_flag
    ):
        """Tests error handling when fix_file itself raises an exception."""
        err_msg = "something wrong!"
        mock_fix_file.side_effect = Exception(err_msg)
        with patch.object(sys, "argv", ["pyward", fix_flag, temp_python_file]), patch(
            "sys.stderr", new=StringIO()
        ) as err:
            with pytest.raises(SystemExit) as e:
                main()

        assert f"Error analyzing {temp_python_file}: {err_msg}" in err.getvalue()
        assert e.value.code == 1
