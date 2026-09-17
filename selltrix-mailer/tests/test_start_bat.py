from pathlib import Path


def test_start_bat_uses_winget_uv_when_path_does_not_include_it() -> None:
    launcher = (Path(__file__).resolve().parents[1] / "START.bat").read_text(encoding="utf-8")

    assert 'set "UV_EXE=%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\\uv.exe"' in launcher
    assert 'if not exist "!UV_EXE!"' in launcher
    assert '"%UV_EXE%" run' in launcher
