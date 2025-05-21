import unittest
from iptv_browser import IPTVBrowser, IPTVChannel, Episode, PlaylistParsingError

class TestIPTVBrowserParsePlaylist(unittest.TestCase):

    def setUp(self):
        self.browser = IPTVBrowser()

    def test_series_parsing_basic(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="series.1" tvg-name="My Awesome Series S01E01" tvg-logo="series.png" group-title="US Series",My Awesome Series S01E01
http://server/series/s01e01.mp4
#EXTINF:-1 tvg-id="series.1" tvg-name="My Awesome Series S01E02" tvg-logo="series.png" group-title="US Series",My Awesome Series S01E02
http://server/series/s01e02.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        
        series_channel = self.browser.channels[0]
        self.assertEqual(series_channel.name, "My Awesome Series")
        self.assertEqual(series_channel.category, "Series")
        self.assertIsNone(series_channel.url) # Series itself has no direct URL
        self.assertEqual(series_channel.logo, "series.png")
        self.assertEqual(series_channel.epg_id, "series.1") # EPG ID from first episode
        self.assertEqual(series_channel.group, "US Series") # Group title from M3U
        
        self.assertEqual(len(series_channel.episodes), 2)
        
        episode1 = series_channel.episodes[0]
        self.assertEqual(episode1.name, "My Awesome Series S01E01")
        self.assertEqual(episode1.url, "http://server/series/s01e01.mp4")
        self.assertEqual(episode1.season_number, 1)
        self.assertEqual(episode1.episode_number, 1)
        
        episode2 = series_channel.episodes[1]
        self.assertEqual(episode2.name, "My Awesome Series S01E02")
        self.assertEqual(episode2.url, "http://server/series/s01e02.mp4")
        self.assertEqual(episode2.season_number, 1)
        self.assertEqual(episode2.episode_number, 2)

    def test_series_name_extraction_fallback_to_group_title(self):
        # Test case where tvg-name might be just "S01E01"
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="S01E01" group-title="Special Series Group",S01E01
http://server/series/s01e01.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        series_channel = self.browser.channels[0]
        # The series_name_regex `^(.*?)\s*[Ss]\d+[Ee]\d+` won't find a name part in "S01E01"
        # So it should fallback to group_title for series_name
        self.assertEqual(series_channel.name, "Special Series Group") 
        self.assertEqual(series_channel.category, "Series")
        self.assertEqual(len(series_channel.episodes), 1)
        self.assertEqual(series_channel.episodes[0].name, "S01E01")
        self.assertEqual(series_channel.episodes[0].season_number, 1)
        self.assertEqual(series_channel.episodes[0].episode_number, 1)

    def test_series_different_logos_per_episode(self):
        # Series should pick up attributes like logo from the *first* episode encountered.
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="Another Series S01E01" tvg-logo="logo1.png" group-title="Series",Another Series S01E01
http://server/series/another/s01e01.mp4
#EXTINF:-1 tvg-name="Another Series S01E02" tvg-logo="logo2.png" group-title="Series",Another Series S01E02
http://server/series/another/s01e02.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        series_channel = self.browser.channels[0]
        self.assertEqual(series_channel.name, "Another Series")
        self.assertEqual(series_channel.logo, "logo1.png") # Logo from the first episode
        self.assertEqual(len(series_channel.episodes), 2)

    def test_movie_parsing(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="movie.123" tvg-name="Awesome Movie" tvg-logo="movie.png" group-title="Movies | HD",Awesome Movie
http://server/movie/123.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        
        movie_channel = self.browser.channels[0]
        self.assertEqual(movie_channel.name, "Awesome Movie")
        self.assertEqual(movie_channel.category, "Movie")
        self.assertEqual(movie_channel.url, "http://server/movie/123.mp4")
        self.assertEqual(movie_channel.logo, "movie.png")
        self.assertEqual(movie_channel.epg_id, "movie.123")
        self.assertEqual(movie_channel.group, "Movies | HD")
        self.assertEqual(len(movie_channel.episodes), 0) # No episodes for movies

    def test_sport_parsing(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="sport.456" tvg-name="Big Game" tvg-logo="sport.png" group-title="Sports | Live",Big Game
http://server/sport/live.m3u8
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        
        sport_channel = self.browser.channels[0]
        self.assertEqual(sport_channel.name, "Big Game")
        self.assertEqual(sport_channel.category, "Sport")
        self.assertEqual(sport_channel.url, "http://server/sport/live.m3u8")
        self.assertEqual(sport_channel.logo, "sport.png")
        self.assertEqual(sport_channel.epg_id, "sport.456")
        self.assertEqual(sport_channel.group, "Sports | Live")

    def test_live_stream_parsing_with_group_title(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="news.789" tvg-name="News Channel" tvg-logo="news.png" group-title="News",News Channel
http://server/news/live.m3u8
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        
        live_channel = self.browser.channels[0]
        self.assertEqual(live_channel.name, "News Channel")
        # Category should be the group-title if not 'series', 'movie', or 'sport'
        self.assertEqual(live_channel.category, "News") 
        self.assertEqual(live_channel.url, "http://server/news/live.m3u8")
        self.assertEqual(live_channel.logo, "news.png")
        self.assertEqual(live_channel.epg_id, "news.789")

    def test_live_stream_parsing_ungrouped(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="other.000" tvg-name="Other Channel",Other Channel
http://server/other/live.m3u8
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        
        live_channel = self.browser.channels[0]
        self.assertEqual(live_channel.name, "Other Channel")
        # Ungrouped channels default to "Live Stream" category
        self.assertEqual(live_channel.category, "Live Stream") 
        self.assertEqual(live_channel.url, "http://server/other/live.m3u8")
        self.assertEqual(live_channel.group, "Ungrouped") # Default group

    def test_attribute_parsing_detailed_all_fields(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="id1" tvg-name="Full Name" tvg-logo="logo.png" group-title="Test Group" tvg-country="US" tvg-language="English",Full Name
http://server/path/stream1
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        channel = self.browser.channels[0]
        self.assertEqual(channel.name, "Full Name")
        self.assertEqual(channel.epg_id, "id1")
        self.assertEqual(channel.logo, "logo.png")
        self.assertEqual(channel.group, "Test Group")
        self.assertEqual(channel.country, "US")
        self.assertEqual(channel.language, "English")
        self.assertEqual(channel.url, "http://server/path/stream1")
        # Category will be "Test Group" as it's not a special keyword like "Movie"
        self.assertEqual(channel.category, "Test Group")

    def test_mixed_content_parsing(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="Action Movie" group-title="Movies",Action Movie
http://server/movie/action.mp4
#EXTINF:-1 tvg-name="Comedy Series S01E01" group-title="Series | Comedy",Comedy Series S01E01
http://server/series/comedy/s01e01.mkv
#EXTINF:-1 tvg-name="Comedy Series S01E02" group-title="Series | Comedy",Comedy Series S01E02
http://server/series/comedy/s01e02.mkv
#EXTINF:-1 tvg-name="Live Sport Event" group-title="Sport",Live Sport Event
http://server/sport/live.ts
#EXTINF:-1 tvg-name="General Channel" group-title="General TV",General Channel
http://server/live/general.m3u8
"""
        self.browser._parse_playlist(m3u_content)
        # Expected: 1 Movie, 1 Series (with 2 episodes), 1 Sport, 1 Live Stream (General TV) = 4 IPTVChannel objects
        self.assertEqual(len(self.browser.channels), 4)

        categories_found = sorted([ch.category for ch in self.browser.channels])
        expected_categories = sorted(["Movie", "Series", "Sport", "General TV"])
        self.assertEqual(categories_found, expected_categories)

        for channel in self.browser.channels:
            if channel.name == "Action Movie":
                self.assertEqual(channel.category, "Movie")
                self.assertEqual(channel.url, "http://server/movie/action.mp4")
            elif channel.name == "Comedy Series":
                self.assertEqual(channel.category, "Series")
                self.assertIsNone(channel.url)
                self.assertEqual(len(channel.episodes), 2)
                self.assertEqual(channel.episodes[0].name, "Comedy Series S01E01")
                self.assertEqual(channel.episodes[0].season_number, 1)
                self.assertEqual(channel.episodes[0].episode_number, 1)
            elif channel.name == "Live Sport Event":
                self.assertEqual(channel.category, "Sport")
            elif channel.name == "General Channel":
                self.assertEqual(channel.category, "General TV") # Treated as a live stream type with its group name as category
    
    def test_series_without_sxxexx_pattern_in_name(self):
        # If group-title is "Series" but name doesn't have SxxExx, it's treated as a regular channel
        # within the "Series" category.
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="Old Series Pilot" group-title="Series Archive",Old Series Pilot
http://server/series/old/pilot.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        channel = self.browser.channels[0]
        self.assertEqual(channel.name, "Old Series Pilot")
        self.assertEqual(channel.category, "Series") # Category is "Series" due to group-title
        self.assertEqual(channel.url, "http://server/series/old/pilot.mp4") # Has a URL
        self.assertEqual(len(channel.episodes), 0) # No episodes parsed for it

    def test_empty_playlist(self):
        m3u_content = "#EXTM3U\n"
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 0)

    def test_malformed_extinf_line(self):
        # This should be skipped, and not break the parser for other valid entries
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="Valid Channel",Valid Channel
http://server/valid
#EXTINF: (this is malformed)
http://server/malformed_url_ignored
#EXTINF:-1,Another Valid Channel
http://server/another_valid
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 2)
        self.assertEqual(self.browser.channels[0].name, "Valid Channel")
        self.assertEqual(self.browser.channels[1].name, "Another Valid Channel")

    def test_no_tvg_name_uses_raw_name(self):
        m3u_content = """#EXTM3U
#EXTINF:-1 group-title="Movies",The Movie Title From Raw
http://server/movie/raw.mp4
"""
        self.browser._parse_playlist(m3u_content)
        self.assertEqual(len(self.browser.channels), 1)
        channel = self.browser.channels[0]
        self.assertEqual(channel.name, "The Movie Title From Raw")
        self.assertEqual(channel.category, "Movie")

if __name__ == '__main__':
    unittest.main()
