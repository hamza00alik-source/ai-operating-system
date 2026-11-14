from ai_os.clipping import TranscriptSegment, rank_clip_candidates, score_text, validate_segments

def test_validate_segments_discards_invalid_and_sorts():
    items = [
        {"start": 4, "end": 7, "text": "second"},
        {"start": -1, "end": 2, "text": "invalid"},
        {"start": 1, "end": 3, "text": "first"},
        {"start": 8, "end": 8, "text": "zero"},
    ]
    result = validate_segments(items)
    assert [item.text for item in result] == ["first", "second"]

def test_score_text_rewards_hook_signals():
    assert score_text("Why is this the biggest mistake?") > score_text("This is a regular sentence")

def test_rank_candidates_returns_non_overlapping_clips():
    segments = [
        TranscriptSegment(0, 8, "Why is this important?"),
        TranscriptSegment(8, 18, "The surprising truth is that it works."),
        TranscriptSegment(40, 50, "This is another interesting moment!"),
        TranscriptSegment(50, 60, "Because the result changes everything."),
    ]
    result = rank_clip_candidates(segments, clip_seconds=25, max_clips=3, min_seconds=12)
    assert len(result) >= 1
    for left, right in zip(result, result[1:]):
        assert left.end <= right.start or left.start >= right.end
