from opencompany_core.media_studio import CapabilityState, video_capabilities


def test_longcat_video_is_registered_but_not_claimed_as_connected():
    item = next(value for value in video_capabilities() if value.key == "longcat-video")
    assert item.state == CapabilityState.RESEARCHED
    assert "text_to_video" in item.generation_modes
    assert any("CUDA" in requirement for requirement in item.execution_requirements)
    assert any("owner approval" in control for control in item.safety_controls)
