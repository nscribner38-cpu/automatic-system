import pytest

from dfs_builder import safe_io


@pytest.fixture(autouse=True)
def isolated_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(safe_io, "BACKUPS", tmp_path / ".backups")
    monkeypatch.setattr(safe_io, "ROOT", tmp_path)


def test_write_returns_checksum_of_disk_contents(tmp_path):
    target = tmp_path / "a.txt"
    digest = safe_io.write_verified(target, "hello\n")
    assert digest == safe_io.sha256_file(target)


def test_existing_file_is_backed_up_before_overwrite(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old\r\n")
    safe_io.write_verified(target, b"new\r\n")
    backups = list((tmp_path / ".backups").rglob("a.txt.*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"old\r\n"
    assert target.read_bytes() == b"new\r\n"  # CRLF preserved byte-for-byte


def test_invalid_python_is_refused_and_nothing_written(tmp_path):
    target = tmp_path / "bad.py"
    with pytest.raises(SyntaxError):
        safe_io.write_verified(target, "def broken(:\n")
    assert not target.exists()


def test_detect_newline():
    assert safe_io.detect_newline(b"a\r\nb\r\n") == "\r\n"
    assert safe_io.detect_newline(b"a\nb\n") == "\n"
