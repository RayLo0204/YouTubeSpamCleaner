from cleaner.launcher import instance_lock


def test_second_instance_does_not_read_a_locked_byte(tmp_path):
    first=instance_lock(tmp_path)
    assert first is not None
    try:
        assert instance_lock(tmp_path) is None
    finally:
        first.close()
    reopened=instance_lock(tmp_path)
    assert reopened is not None
    reopened.close()
