"""Tests des fonctions pures de déduction des métadonnées."""

from lofima.metadata import clean_title, guess_tags, split_artist_title


def test_clean_title_removes_noise_but_keeps_useful_info():
    assert clean_title("One More Time (Official Video)") == "One More Time"
    assert clean_title("Song [Lyrics] (feat. X)") == "Song (feat. X)"
    assert clean_title("Song (Remix)") == "Song (Remix)"


def test_split_artist_title():
    assert split_artist_title("Daft Punk - One More Time") == ("Daft Punk", "One More Time")
    assert split_artist_title("Just A Title") == ("", "Just A Title")


def test_guess_tags_from_video_title():
    tags = guess_tags({"title": "Daft Punk - One More Time (Official Video)", "channel": "x",
                       "upload_date": "20090101", "webpage_url": "https://y"})
    assert (tags.artist, tags.title, tags.year, tags.comment) == ("Daft Punk", "One More Time", "2009", "https://y")


def test_guess_tags_prefers_youtube_music_fields():
    tags = guess_tags({"title": "whatever", "track": "Get Lucky", "artist": "Daft Punk",
                       "album": "Random Access Memories", "release_year": 2013})
    assert (tags.title, tags.artist, tags.album, tags.year) == ("Get Lucky", "Daft Punk", "Random Access Memories", "2013")


def test_guess_tags_falls_back_to_channel_without_topic_suffix():
    tags = guess_tags({"title": "Lofi beat", "channel": "Chill Guy - Topic"})
    assert (tags.artist, tags.title) == ("Chill Guy", "Lofi beat")
