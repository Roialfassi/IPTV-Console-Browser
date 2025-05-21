import requests
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json
import os
import io
import subprocess
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from rich import print as rprint
import platform
from fuzzywuzzy import fuzz
from collections import defaultdict
import logging
from urllib.parse import urlparse
import shutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='iptv_browser.log'
)


@dataclass
class Episode:
    name: str
    url: str
    season_number: Optional[int] = None
    episode_number: Optional[int] = None


@dataclass
class IPTVChannel:
    name: str
    group: str
    url: str
    logo: Optional[str] = None
    epg_id: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None  # Added category
    episodes: List[Episode] = field(default_factory=list)  # Added episodes field


class URLValidationError(Exception):
    pass


class VLCNotFoundError(Exception):
    pass


class PlaylistParsingError(Exception):
    pass


class IPTVBrowser:
    def __init__(self):
        self.playlist_url = None
        self.channels: List[IPTVChannel] = []
        self.console = Console()
        self.current_filter = None

    def validate_url(self, url: str) -> bool:
        """Validate URL format and accessibility"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logging.error(f"URL validation error: {e}")
            return False

    def setup_vlc(self) -> Tuple[str, bool]:
        """Setup and verify VLC installation"""
        system = platform.system()
        vlc_paths = {
            "Windows": [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            ],
            "Darwin": [
                "/Applications/VLC.app/Contents/MacOS/VLC"
            ],
            "Linux": [
                "/usr/bin/vlc",
                "/usr/local/bin/vlc"
            ]
        }

        # Check if 'vlc' is in PATH
        vlc_in_path = shutil.which("vlc")
        if vlc_in_path:
            return vlc_in_path, True

        # Check system-specific paths
        if system in vlc_paths:
            for path in vlc_paths[system]:
                if os.path.isfile(path):
                    return path, True

        return "", False

    def fetch_playlist(self, url: str) -> bool:
        """Fetch and parse the M3U playlist with error handling"""
        try:
            if not self.validate_url(url):
                raise URLValidationError("Invalid URL format")

            self.playlist_url = url
            response = requests.get(url, stream=True, timeout=10)
            response.raise_for_status()

            content = response.text
            if not content.strip().startswith('#EXTM3U'):
                raise PlaylistParsingError("Invalid M3U format: Missing #EXTM3U header")

            self._parse_playlist(content)
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Network error: {e}")
            raise
        except PlaylistParsingError as e:
            logging.error(f"Parsing error: {e}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise

    def parse_playlist_from_content(self, content: str) -> bool:
        """Parse M3U playlist content from a string with error handling."""
        try:
            if not content.strip().startswith('#EXTM3U'):
                raise PlaylistParsingError("Invalid M3U format: Missing #EXTM3U header")
            
            # Reset channels before parsing new content
            self.channels = [] 
            self.playlist_url = None # Reset playlist URL as we are loading from content

            self._parse_playlist(content)
            
            if not self.channels:
                # This case might be covered by _parse_playlist raising an error if content is bad
                # but an explicit check if no channels were parsed can be useful.
                # However, _parse_playlist already handles logging, so maybe just check len.
                logging.info("Playlist parsed, but no channels were loaded.")
            
            return True # Success if parsing completed, even if no channels found (empty valid playlist)

        except PlaylistParsingError as e: # Catch specific error from _parse_playlist or header check
            logging.error(f"Content parsing error: {e}")
            raise # Re-raise for the GUI to handle
        except Exception as e: # Catch any other unexpected errors during parsing
            logging.error(f"Unexpected error during content parsing: {e}")
            # Encapsulate unexpected errors into PlaylistParsingError for consistent error handling by caller
            raise PlaylistParsingError(f"Unexpected error processing playlist content: {e}")


    def _parse_playlist(self, content: str):
        """Parse playlist content with error handling"""
        try:
            patterns = {
                'name': re.compile(r'tvg-name="([^"]*)"'),
                'group': re.compile(r'group-title="([^"]*)"'),
                'logo': re.compile(r'tvg-logo="([^"]*)"'),
                'epg_id': re.compile(r'tvg-id="([^"]*)"'),
                'country': re.compile(r'tvg-country="([^"]*)"'),
                'language': re.compile(r'tvg-language="([^"]*)"')
            }
            # Regex to find SxxExx pattern and extract season/episode numbers
            series_episode_meta_regex = re.compile(r'[Ss](\d+)[Ee](\d+)')
            # Regex to extract the series name part from a string like "Series Name S01E01"
            series_name_regex = re.compile(r'^(.*?)\s*[Ss]\d+[Ee]\d+', re.IGNORECASE)


            self.channels = []
            series_channels_map: Dict[str, IPTVChannel] = {} # To group episodes under a single series entry
            
            buffer = io.StringIO(content)
            buffer.readline()  # Skip #EXTM3U line

            extinf_line = None
            line_number = 1

            for line_content in buffer:
                line_number += 1
                line_content = line_content.strip()
                if not line_content:
                    continue

                if line_content.startswith('#EXTINF:'):
                    extinf_line = line_content
                elif extinf_line and not line_content.startswith('#'):
                    # This is the URL line
                    channel_url = line_content
                    try:
                        # Extract common attributes
                        raw_name = extinf_line.split(',')[-1].strip()
                        tvg_name_match = patterns['name'].search(extinf_line)
                        name = tvg_name_match.group(1) if tvg_name_match else raw_name

                        group_match = patterns['group'].search(extinf_line)
                        group_title = group_match.group(1) if group_match else "Ungrouped"
                        
                        logo_match = patterns['logo'].search(extinf_line)
                        logo = logo_match.group(1) if logo_match else None
                        
                        epg_id_match = patterns['epg_id'].search(extinf_line)
                        epg_id = epg_id_match.group(1) if epg_id_match else None

                        country_match = patterns['country'].search(extinf_line)
                        country = country_match.group(1) if country_match else None

                        language_match = patterns['language'].search(extinf_line)
                        language = language_match.group(1) if language_match else None
                        
                        category = "Live Stream" # Default category

                        # Categorization Logic
                        if "series" in group_title.lower():
                            category = "Series"
                            
                            # Try to extract season and episode numbers
                            episode_meta_match = series_episode_meta_regex.search(name)
                            
                            if episode_meta_match:
                                season_number = int(episode_meta_match.group(1))
                                episode_number = int(episode_meta_match.group(2))
                                episode_name = name # Use full original name for the episode
                                
                                # Try to extract series name using the specific regex
                                series_name_match = series_name_regex.match(name)
                                if series_name_match and series_name_match.group(1).strip():
                                    series_name = series_name_match.group(1).strip()
                                else:
                                    # Fallback if series name part is empty or regex doesn't match structure
                                    series_name = group_title 

                                if series_name not in series_channels_map:
                                    # Create the parent series channel if it doesn't exist
                                    series_channels_map[series_name] = IPTVChannel(
                                        name=series_name,
                                        group=group_title,
                                        url=None, # Series itself might not have a direct URL
                                        logo=logo, # Use logo from the first encountered episode for the series
                                        epg_id=epg_id, # Use EPG ID from the first encountered episode
                                        country=country,
                                        language=language,
                                        category=category
                                    )
                                
                                # Create and add the episode
                                episode = Episode(
                                    name=episode_name,
                                    url=channel_url,
                                    season_number=season_number,
                                    episode_number=episode_number
                                )
                                series_channels_map[series_name].episodes.append(episode)
                            else:
                                # It's in a series group but name doesn't match SxxExx pattern,
                                # treat as a regular channel under "Series" category for now.
                                # Or, could decide to log this as unparsable episode.
                                regular_series_channel = IPTVChannel(
                                    name=name, group=group_title, url=channel_url, logo=logo,
                                    epg_id=epg_id, country=country, language=language, category=category
                                )
                                self.channels.append(regular_series_channel)
                        
                        elif "movie" in group_title.lower():
                            category = "Movie"
                            channel = IPTVChannel(
                                name=name, group=group_title, url=channel_url, logo=logo,
                                epg_id=epg_id, country=country, language=language, category=category
                            )
                            self.channels.append(channel)

                        elif "sport" in group_title.lower():
                            category = "Sport"
                            channel = IPTVChannel(
                                name=name, group=group_title, url=channel_url, logo=logo,
                                epg_id=epg_id, country=country, language=language, category=category
                            )
                            self.channels.append(channel)
                        
                        else: # Default to Live Stream or use group_title if specific keywords not found
                            category = group_title if group_title != "Ungrouped" else "Live Stream"
                            channel = IPTVChannel(
                                name=name, group=group_title, url=channel_url, logo=logo,
                                epg_id=epg_id, country=country, language=language, category=category
                            )
                            self.channels.append(channel)

                    except Exception as e:
                        logging.warning(f"Error parsing channel at line {line_number}: {e}. EXTINF: '{extinf_line}', URL: '{channel_url}'")
                    finally:
                        extinf_line = None
            
            # Add all collected series (with their episodes) to the main channels list
            self.channels.extend(series_channels_map.values())

        except Exception as e:
            logging.error(f"Playlist parsing error: {e}")
            raise PlaylistParsingError(f"Failed to parse playlist: {e}")

    def search_channels(self, query: str) -> List[IPTVChannel]:
        """Search channels with error handling"""
        try:
            query = query.strip().lower()
            if not query:
                return []

            results = []
            for channel in self.channels:
                try:
                    ratio = fuzz.partial_ratio(query, channel.name.lower())
                    if ratio > 80:
                        results.append(channel)
                except Exception as e:
                    logging.warning(f"Error matching channel {channel.name}: {e}")
                    continue
            return results

        except Exception as e:
            logging.error(f"Search error: {e}")
            return []

    def play_channel(self, channel: IPTVChannel) -> bool:
        """Play channel with error handling"""
        try:
            vlc_path, vlc_exists = self.setup_vlc()
            if not vlc_exists:
                raise VLCNotFoundError("VLC media player not found")

            subprocess.Popen([vlc_path, channel.url],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True

        except VLCNotFoundError as e:
            logging.error(f"VLC error: {e}")
            raise
        except Exception as e:
            logging.error(f"Playback error: {e}")
            raise

    def display_channels(self, channels: List[IPTVChannel]):
        """Display channels or series with error handling"""
        try:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim")
            table.add_column("Name")
            table.add_column("Category", justify="left")
            table.add_column("Details", justify="left")
            table.add_column("Language", justify="right")

            for idx, item in enumerate(channels, 1):
                try:
                    details = ""
                    if item.category == "Series":
                        details = f"{len(item.episodes)} episodes"
                    elif item.url: # For Movies, Sports, Live Streams
                        details = "Playable"
                    
                    table.add_row(
                        str(idx),
                        item.name,
                        item.category or "N/A",
                        details,
                        item.language or "N/A"
                    )
                except Exception as e:
                    logging.warning(f"Error displaying item {item.name}: {e}")
                    continue

            self.console.print(table)

        except Exception as e:
            logging.error(f"Display error: {e}")
            self.console.print("[red]Error displaying items[/red]")

    def group_channels(self) -> Dict[str, List[IPTVChannel]]:
        """Group channels by category with error handling"""
        try:
            categories = defaultdict(list)
            for channel in self.channels:
                categories[channel.category or "Uncategorized"].append(channel)
            return dict(categories)
        except Exception as e:
            logging.error(f"Grouping error: {e}")
            return {"Error": []}

    def main_menu(self):
        """Main menu with error handling"""
        while True:
            try:
                self.console.clear()
                self.console.print(Panel.fit(
                    "IPTV Browser\n\n"
                    "[1] View All Channels\n"
                    "[2] Browse by Category\n"
                    "[3] Search Channels\n"
                    "[4] Exit",
                    title="Main Menu"
                ))

                choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4"])

                if choice == "1":
                    self.browse_channels(self.channels)
                elif choice == "2":
                    self.browse_categories()
                elif choice == "3":
                    self.search_menu()
                elif choice == "4":
                    break

            except KeyboardInterrupt:
                if Prompt.ask("\nDo you want to exit?", choices=["y", "n"]) == "y":
                    break
            except Exception as e:
                logging.error(f"Menu error: {e}")
                self.console.print("[red]An error occurred. Please try again.[/red]")
                input("Press Enter to continue...")

    def display_episodes(self, series_channel: IPTVChannel):
        """Display episodes of a series and allow selection for playback."""
        if not series_channel.episodes:
            self.console.print("[yellow]No episodes found for this series.[/yellow]")
            input("Press Enter to continue...")
            return

        while True:
            try:
                self.console.clear()
                self.console.print(Panel(f"Episodes for: {series_channel.name}", title="Episode List"))
                
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("#", style="dim")
                table.add_column("Episode Name")
                table.add_column("Season", justify="right")
                table.add_column("Episode", justify="right")

                for idx, episode in enumerate(series_channel.episodes, 1):
                    table.add_row(
                        str(idx),
                        episode.name,
                        str(episode.season_number) if episode.season_number is not None else "N/A",
                        str(episode.episode_number) if episode.episode_number is not None else "N/A"
                    )
                self.console.print(table)
                
                choice = Prompt.ask("\nEnter episode number to play, or 'b' for back", default="b")

                if choice.lower() == 'b':
                    break
                
                idx = int(choice) - 1
                if 0 <= idx < len(series_channel.episodes):
                    selected_episode = series_channel.episodes[idx]
                    # Assuming play_channel can handle an object with a .url attribute
                    self.play_channel(selected_episode) 
                else:
                    self.console.print("[red]Invalid episode number[/red]")
                    input("Press Enter to continue...")

            except ValueError:
                self.console.print("[red]Invalid input. Please enter a number or 'b'.[/red]")
                input("Press Enter to continue...")
            except VLCNotFoundError: # Already handled in play_channel, but good to be explicit
                self.console.print("[red]Error: VLC media player not found[/red]")
                input("Press Enter to continue...")
                break # Break from episode display on VLC error
            except Exception as e:
                logging.error(f"Episode display/playback error: {e}")
                self.console.print("[red]An error occurred during episode selection or playback.[/red]")
                input("Press Enter to continue...")


    def browse_channels(self, channels: List[IPTVChannel]):
        """Browse channels and series with error handling"""
        while True:
            try:
                self.console.clear()
                self.display_channels(channels) # This now shows category and episode count for series
                choice = Prompt.ask("\nEnter item number to play or view episodes, 'b' for back", default="b")

                if choice.lower() == 'b':
                    break

                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(channels):
                        selected_item = channels[idx]
                        if selected_item.category == "Series" and selected_item.episodes:
                            self.display_episodes(selected_item)
                        elif selected_item.url: # Playable item (Movie, Sport, Live Stream, or Series fallback)
                            self.play_channel(selected_item)
                        else:
                            self.console.print("[yellow]This item is not directly playable and has no episodes listed.[/yellow]")
                            input("Press Enter to continue...")
                    else:
                        self.console.print("[red]Invalid item number[/red]")
                except ValueError:
                    self.console.print("[red]Invalid input[/red]")

            except KeyboardInterrupt:
                break
            except VLCNotFoundError: # This might be redundant if play_channel handles it and re-raises
                self.console.print("[red]Error: VLC media player not found[/red]")
                input("Press Enter to continue...")
            except Exception as e:
                logging.error(f"Browse error: {e}")
                self.console.print("[red]An error occurred. Please try again.[/red]")
                input("Press Enter to continue...")

    def browse_categories(self):
        """Browse channels grouped by category with error handling"""
        try:
            categories = self.group_channels() # This now returns Dict[str, List[IPTVChannel]] by category
            if not categories or "Error" in categories:
                self.console.print("[yellow]No categories found or error in grouping.[/yellow]")
                input("Press Enter to continue...")
                return

            while True:
                self.console.clear()
                self.console.print(Panel("Browse by Category", title="Categories"))
                category_names = list(categories.keys())
                for idx, name in enumerate(category_names, 1):
                    self.console.print(f"[{idx}] {name} ({len(categories[name])} items)")

                choice = Prompt.ask("\nSelect category number, 'b' for back", default="b")

                if choice.lower() == 'b':
                    break

                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(category_names):
                        selected_category_name = category_names[idx]
                        self.browse_channels(categories[selected_category_name])
                    else:
                        self.console.print("[red]Invalid category number[/red]")
                except (ValueError, IndexError):
                    self.console.print("[red]Invalid input. Please enter a number or 'b'.[/red]")

        except Exception as e:
            logging.error(f"Category browse error: {e}")
            self.console.print("[red]An error occurred while browsing categories[/red]")
            input("Press Enter to continue...")

    def search_menu(self):
        """Search menu with error handling"""
        while True:
            try:
                self.console.clear()
                query = Prompt.ask("\nEnter search term (or 'b' for back)")

                if query.lower() == 'b':
                    break

                results = self.search_channels(query)
                if results:
                    self.browse_channels(results)
                else:
                    self.console.print("[yellow]No channels found[/yellow]")
                    input("Press Enter to continue...")

            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Search error: {e}")
                self.console.print("[red]An error occurred during search[/red]")
                input("Press Enter to continue...")


def main():
    browser = IPTVBrowser()
    console = Console()

    while True:
        try:
            url = Prompt.ask("Enter M3U playlist URL (or 'q' to quit)")
            if url.lower() == 'q':
                break

            console.print("Validating and fetching playlist...")
            browser.fetch_playlist(url)

            if browser.channels:
                console.print(f"[green]Successfully loaded {len(browser.channels)} channels[/green]")
                browser.main_menu()
                break
            else:
                console.print("[yellow]No channels found in playlist[/yellow]")

        except URLValidationError:
            console.print("[red]Error: Invalid URL format[/red]")
        except requests.exceptions.RequestException:
            console.print("[red]Error: Could not fetch playlist. Check your internet connection and URL[/red]")
        except PlaylistParsingError:
            console.print("[red]Error: Invalid playlist format[/red]")
        except KeyboardInterrupt:
            if Prompt.ask("\nDo you want to quit?", choices=["y", "n"]) == "y":
                break
        except Exception as e:
            logging.error(f"Main error: {e}")
            console.print("[red]An unexpected error occurred[/red]")


if __name__ == "__main__":
    main()
