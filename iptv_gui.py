import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFileDialog,
                             QListWidget, QListWidgetItem) # Added QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QSize # Added QSize for potential future use

import subprocess # Added for VLC
from PyQt5.QtWidgets import QMessageBox # Added for error dialogs

# Assuming iptv_browser.py is in the same directory or Python path
try:
    from iptv_browser import IPTVBrowser, PlaylistParsingError, URLValidationError, IPTVChannel, Episode, VLCNotFoundError
except ImportError:
    # Fallback for environments where the script is not in the Python path directly
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from iptv_browser import IPTVBrowser, PlaylistParsingError, URLValidationError, IPTVChannel, Episode, VLCNotFoundError
import requests # For requests.exceptions.RequestException

class IPTVApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.browser = IPTVBrowser()
        self.current_selected_series: Optional[IPTVChannel] = None
        self.current_category_name: Optional[str] = None
        self.grouped_channels_data = {}

        self.setWindowTitle("IPTV Browser GUI")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        self.base_window_title = "IPTV Browser GUI"
        self.setWindowTitle(self.base_window_title)
        self.setGeometry(100, 100, 850, 650) # Slightly larger default size

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)


        # Input Layout
        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter M3U Playlist URL")
        input_layout.addWidget(self.url_input)
        self.load_url_button = QPushButton("Load from URL")
        self.load_url_button.clicked.connect(self.load_from_url)
        input_layout.addWidget(self.load_url_button)
        self.load_file_button = QPushButton("Load from File")
        self.load_file_button.clicked.connect(self.load_from_file)
        input_layout.addWidget(self.load_file_button)
        self.main_layout.addLayout(input_layout)

        # Status Label
        self.status_label = QLabel("Ready. Enter URL or load a file.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(30) # Give it some space
        self.main_layout.addWidget(self.status_label)

        # Back Button (initially hidden)
        self.back_button = QPushButton("Back to Category View")
        self.back_button.clicked.connect(self.show_items_in_current_category)
        self.back_button.hide()
        self.main_layout.addWidget(self.back_button)

        # Search Bar for items
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search current list...")
        self.search_bar.textChanged.connect(self.filter_items_in_list)
        self.main_layout.addWidget(self.search_bar)

        # Browsing Area (Category List and Item List)
        browse_layout = QHBoxLayout()
        browse_layout.setSpacing(10)
        self.category_list_widget = QListWidget()
        self.category_list_widget.setMaximumWidth(250) # Slightly wider
        self.category_list_widget.setAlternatingRowColors(True)
        self.category_list_widget.setStyleSheet("QListWidget::item { padding: 3px; }")
        self.category_list_widget.currentItemChanged.connect(self.on_category_selected)
        browse_layout.addWidget(self.category_list_widget, 2) # Adjusted stretch factor

        self.item_list_widget = QListWidget()
        self.item_list_widget.setAlternatingRowColors(True)
        self.item_list_widget.setStyleSheet("QListWidget::item { padding: 5px; }")
        self.item_list_widget.itemClicked.connect(self.on_item_selected)
        browse_layout.addWidget(self.item_list_widget, 5) # Adjusted stretch factor
        
        self.main_layout.addLayout(browse_layout)
        
        # Set initial UI state (e.g. disabled lists until load)
        self._set_loading_state(False) # Enable inputs, disable lists initially


    def _set_loading_state(self, is_loading):
        """Enable/disable UI elements during loading."""
        self.url_input.setEnabled(not is_loading)
        self.load_url_button.setEnabled(not is_loading)
        self.load_file_button.setEnabled(not is_loading)
        self.search_bar.setEnabled(not is_loading)
        self.category_list_widget.setEnabled(not is_loading)
        self.item_list_widget.setEnabled(not is_loading)
        
        if is_loading:
            self.category_list_widget.clear() # Clear lists during load
            self.item_list_widget.clear()
            # Optionally, display a "Loading..." message in list widgets
            # self._show_message_in_list_widget(self.category_list_widget, "Loading categories...")
            # self._show_message_in_list_widget(self.item_list_widget, "Loading items...")

    def _show_message_in_list_widget(self, list_widget: QListWidget, message: str):
        list_widget.clear()
        item = QListWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled) # Make it non-interactive
        item.setTextAlignment(Qt.AlignCenter)
        list_widget.addItem(item)

    def populate_categories(self):
        self.search_bar.clear()
        self.category_list_widget.clear()
        self.item_list_widget.clear()
        self.back_button.hide()
        self.current_selected_series = None
        self.current_category_name = None
        self.setWindowTitle(self.base_window_title)


        if not self.browser.channels:
            self.status_label.setText("<font color='orange'>No channels loaded to populate categories.</font>")
            self._show_message_in_list_widget(self.category_list_widget, "Load a playlist to see categories.")
            self._show_message_in_list_widget(self.item_list_widget, "Select a category to see items.")
            return

        try:
            self.grouped_channels_data = self.browser.group_channels()
        except Exception as e: # Catch potential errors from group_channels
            self.status_label.setText(f"<font color='red'>Error grouping channels: {e}</font>")
            self.grouped_channels_data = {}
            self._show_message_in_list_widget(self.category_list_widget, "Error grouping channels.")
            return
        
        if not self.grouped_channels_data or ("Error" in self.grouped_channels_data and not any(k for k in self.grouped_channels_data if k != "Error")):
            self.status_label.setText("<font color='red'>Playlist parsed, but no categories found or error in grouping.</font>")
            self.grouped_channels_data = {} # Ensure it's empty
            self._show_message_in_list_widget(self.category_list_widget, "No categories found.")
            self.filter_items_in_list() # This will show "No items to display" in item list
            return

        for category_name_key in sorted(self.grouped_channels_data.keys()):
            if category_name_key == "Error" and len(self.grouped_channels_data[category_name_key]) == 0 : continue # Skip empty error group
            self.category_list_widget.addItem(category_name_key)
        
        if self.category_list_widget.count() > 0:
            self.category_list_widget.setCurrentRow(0)
        else:
            self._show_message_in_list_widget(self.category_list_widget, "No categories available.")
            self.filter_items_in_list() 


    def on_category_selected(self, current_qlist_item, previous_qlist_item):
        self.search_bar.clear()
        if current_qlist_item is None:
            self.item_list_widget.clear()
            self.current_category_name = None
            self.setWindowTitle(self.base_window_title)
            self.filter_items_in_list() 
            return

        self.current_category_name = current_qlist_item.text()
        self.back_button.hide() 
        self.current_selected_series = None 
        self.status_label.setText(f"Category: {self.current_category_name}")
        self.setWindowTitle(f"{self.base_window_title} - {self.current_category_name}")
        self.filter_items_in_list() 


    def on_item_selected(self, qlist_item_clicked):
        self.search_bar.clear() 
        data_object = qlist_item_clicked.data(Qt.UserRole)

        if isinstance(data_object, IPTVChannel): 
            if data_object.category == "Series" and data_object.episodes:
                self.current_selected_series = data_object
                self.status_label.setText(f"Series: {data_object.name} - Episodes")
                self.setWindowTitle(f"{self.base_window_title} - {data_object.name}")
                self.back_button.show()
                self.filter_items_in_list() 
            else: 
                if data_object.url:
                    self.play_media(data_object.url, data_object.name)
                else:
                    self.status_label.setText(f"<font color='orange'>Selected: {data_object.name}. No playable URL.</font>")
        
        elif isinstance(data_object, Episode): 
            if data_object.url:
                self.play_media(data_object.url, data_object.name)
            else: 
                 self.status_label.setText(f"<font color='orange'>Selected episode: {data_object.name}. No playable URL.</font>")

    def play_media(self, url: str, item_name: str):
        """Attempts to play the given URL using VLC."""
        try:
            vlc_path, vlc_exists = self.browser.setup_vlc()
            if not vlc_exists:
                raise VLCNotFoundError("VLC media player not found (path check failed).")

            self.status_label.setText(f"Attempting to play: {item_name}...")
            QApplication.processEvents() 

            # Detach process on Linux/macOS, specific flags for Windows if needed
            popen_kwargs = {}
            if sys.platform != "win32":
                popen_kwargs['start_new_session'] = True
            else: # On Windows, DETACHED_PROCESS or CREATE_NEW_CONSOLE might be used
                  # For simplicity, let default Popen behavior handle it, 
                  # but more robust solution might involve win32api.
                  pass

            subprocess.Popen([vlc_path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **popen_kwargs)
            self.status_label.setText(f"Playing: {item_name}")

        except VLCNotFoundError: 
            QMessageBox.critical(self, "VLC Not Found",
                                 "VLC media player not found. Please install VLC and ensure it's in your system PATH or standard installation locations.")
            self.status_label.setText("<font color='red'>Error: VLC not found.</font>")
        except Exception as e:
            QMessageBox.warning(self, "Playback Error",
                                f"Could not start playback for {item_name}: {e}")
            self.status_label.setText(f"<font color='red'>Error playing {item_name}: {e}</font>")


    def show_items_in_current_category(self):
        self.search_bar.clear() 
        if self.current_category_name is None:
            self.status_label.setText("<font color='red'>Error: No category context for back action.</font>")
            # Potentially reset to a base state if this happens
            self.populate_categories() #This will clear things if no channels
            return

        self.back_button.hide()
        self.current_selected_series = None
        self.status_label.setText(f"Category: {self.current_category_name}")
        self.setWindowTitle(f"{self.base_window_title} - {self.current_category_name}")
        self.filter_items_in_list() 

    def filter_items_in_list(self):
        search_text = self.search_bar.text().lower()
        self.item_list_widget.clear()

        source_list = []
        is_episode_view = False
        current_context_name = ""


        if self.current_selected_series:
            source_list = self.current_selected_series.episodes
            is_episode_view = True
            current_context_name = self.current_selected_series.name
        elif self.current_category_name:
            source_list = self.grouped_channels_data.get(self.current_category_name, [])
            current_context_name = self.current_category_name
        else: # No context, list should be empty
            self._show_message_in_list_widget(self.item_list_widget, "Select a category or load a playlist.")
            return
        
        count = 0
        for item_obj in source_list:
            if search_text in item_obj.name.lower():
                count +=1
                display_text = ""
                if is_episode_view and isinstance(item_obj, Episode):
                    s_num = f"S{item_obj.season_number:02}" if item_obj.season_number is not None else ""
                    e_num = f"E{item_obj.episode_number:02}" if item_obj.episode_number is not None else ""
                    sep = " " if s_num and e_num else "" # Only add space if both S and E numbers are present
                    # Ensure that episode name is part of display text if S/E numbers are not present
                    ep_name_part = item_obj.name
                    if s_num or e_num: # If we have S/E numbers, the name might be redundant if it's just "Series S01E01"
                        # This logic can be tricky, assume item_obj.name is the full title for now
                        pass # Using full name as part of SxxExx - name
                    display_text = f"{s_num}{sep}{e_num} - {ep_name_part}".strip().strip("-").strip()
                    if not display_text : display_text = item_obj.name # Fallback to full name if constructed is empty
                
                elif not is_episode_view and isinstance(item_obj, IPTVChannel):
                    display_text = item_obj.name
                    if item_obj.category == "Series" and item_obj.episodes:
                        display_text = f"{item_obj.name} ({len(item_obj.episodes)} episodes)"
                else:
                    continue 

                list_item_widget_gui = QListWidgetItem(display_text)
                list_item_widget_gui.setData(Qt.UserRole, item_obj)
                self.item_list_widget.addItem(list_item_widget_gui)
        
        if count == 0:
            if search_text:
                self._show_message_in_list_widget(self.item_list_widget, f"No results found for '{search_text}'.")
            elif not source_list: # Source list itself was empty
                 self._show_message_in_list_widget(self.item_list_widget, f"No items in {current_context_name}.")
            else: # Source list had items, but search cleared them (e.g. empty search text but something went wrong)
                 self._show_message_in_list_widget(self.item_list_widget, "No items to display.")


    def load_from_url(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("<font color='red'>Error: URL cannot be empty.</font>")
            self.browser.channels = [] # Ensure browser state is also clean
            self.populate_categories() 
            return

        self.status_label.setText("Loading from URL...")
        self._set_loading_state(True)
        QApplication.processEvents() 
        
        self.browser.channels = [] 
        # self.populate_categories() # This clears UI and resets state, called by _set_loading_state implicitly if lists cleared

        try:
            self.browser.fetch_playlist(url) 
            if self.browser.channels:
                self.status_label.setText(f"<font color='green'>Successfully loaded {len(self.browser.channels)} channels from URL.</font>")
            else:
                self.status_label.setText("<font color='orange'>Playlist loaded, but no channels found.</font>")
        except URLValidationError as e:
            self.status_label.setText(f"<font color='red'>Error: Invalid URL - {e}</font>")
        except requests.exceptions.RequestException as e:
            self.status_label.setText(f"<font color='red'>Error: Could not fetch playlist - {e}</font>")
        except PlaylistParsingError as e:
            self.status_label.setText(f"<font color='red'>Error: Could not parse playlist - {e}</font>")
        except Exception as e:
            self.status_label.setText(f"<font color='red'>An unexpected error occurred: {e}</font>")
        finally:
            self._set_loading_state(False)
            self.populate_categories() # Populate based on new data (or lack thereof)


    def load_from_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open M3U Playlist File", "",
                                                   "M3U Files (*.m3u *.m3u8);;All Files (*)", options=options)
        if not file_path:
            self.status_label.setText("File loading cancelled.")
            # No need to clear browser.channels if nothing was attempted
            self.populate_categories() # Ensure UI resets correctly if it had prior state
            return

        self.status_label.setText(f"Loading from file: {os.path.basename(file_path)}...")
        self._set_loading_state(True)
        QApplication.processEvents()
        
        self.browser.channels = [] 
        # self.populate_categories() 

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            self.browser.parse_playlist_from_content(content) 
            
            if self.browser.channels:
                self.status_label.setText(f"<font color='green'>Successfully loaded {len(self.browser.channels)} channels from file.</font>")
            else:
                self.status_label.setText("<font color='orange'>Playlist file processed, but no channels found.</font>")
        except FileNotFoundError: # Specific error
            self.status_label.setText(f"<font color='red'>Error: File not found - {file_path}</font>")
        except IOError as e: # More general I/O errors
             self.status_label.setText(f"<font color='red'>Error reading file {file_path}: {e}</font>")
        except PlaylistParsingError as e: # Parsing error from our browser logic
            self.status_label.setText(f"<font color='red'>Error: Could not parse playlist file - {e}</font>")
        except Exception as e: # Catch-all for other unexpected errors
            self.status_label.setText(f"<font color='red'>An unexpected error occurred while loading the file: {e}</font>")
        finally:
            self._set_loading_state(False)
            self.populate_categories() 

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IPTVApp()
    window.show()
    sys.exit(app.exec_())
