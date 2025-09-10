import os
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QRadioButton, QGroupBox, QListWidget, QListWidgetItem,
                             QFileDialog, QMessageBox, QTextEdit, QLabel, QInputDialog, QCheckBox,
                             QSizePolicy, QTabWidget, QSpinBox)
from PyQt6.QtCore import Qt, QTimer
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import time

# YouTube API scopes and service object
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
service = None

# Global variables for the application
spam_keywords = []
spam_file = "spam_keywords.txt"
selected_comments = []

def login():
    """Handles the user login and authorization process for the YouTube API."""
    global service
    try:
        creds_file = QFileDialog.getOpenFileName(None, "Select client_secret.json", "", "JSON files (*.json)")[0]
        if not creds_file:
            QMessageBox.warning(None, "Warning", "You must select a client_secret.json file.")
            return False
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0)
        service = build("youtube", "v3", credentials=creds)
        QMessageBox.information(None, "Login", "Login successful!")
        return True
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Login failed: {e}")
        return False

def load_keywords():
    """Loads spam keywords from the local file."""
    global spam_keywords
    if os.path.exists(spam_file):
        with open(spam_file, "r", encoding="utf-8") as f:
            spam_keywords = [line.strip() for line in f if line.strip()]
    return spam_keywords

def save_keywords(keywords, list_widget):
    """Saves spam keywords to the local file."""
    with open(spam_file, "w", encoding="utf-8") as f:
        for word in keywords:
            f.write(word + "\n")
    QMessageBox.information(None, "Saved", "Spam keywords saved successfully.")
    list_widget.clear()
    for word in keywords:
        list_widget.addItem(word)

def get_comment_threads(video_id=None, channel_id=None):
    """Fetches comment threads from a specified video or channel."""
    if video_id and channel_id:
        return None, "Please enter only one of Video ID or Channel ID."
    if not video_id and not channel_id:
        return None, "Please enter a Video ID or Channel ID."
    if not service:
        return None, "Please login first."

    comments = []
    page_token = None
    max_pages = 2
    page_count = 0

    while True:
        try:
            request = service.commentThreads().list(
                part="snippet",
                videoId=video_id if video_id else None,
                allThreadsRelatedToChannelId=channel_id if channel_id else None,
                maxResults=20,
                order="time",
                pageToken=page_token
            )
            response = request.execute()
            comments.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            page_count += 1
            if not page_token or page_count >= max_pages:
                break
            time.sleep(0.5)
        except Exception as e:
            return None, f"Failed to fetch comments: {e}"
    return comments, None

class YouTubeSpamCleaner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Spam Cleaner")
        self.setMinimumSize(800, 1000)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timer = None
        self.is_scheduled = False
        self.setup_ui()
        load_keywords()
        self.update_keyword_list()
        self.output_text.append(f"Loaded {len(spam_keywords)} keywords: {', '.join(spam_keywords) if spam_keywords else 'None'}")
        self.set_sections_enabled(False)

    def set_sections_enabled(self, enabled):
        self.input_group.setEnabled(enabled)
        self.action_group.setEnabled(enabled)
        self.keyword_group.setEnabled(enabled)
        self.comment_group.setEnabled(enabled)
        self.output_group.setEnabled(enabled)
        self.list_btn.setEnabled(enabled)
        self.process_selected_btn.setEnabled(enabled)
        style_enabled = "QGroupBox { font-weight: bold; color: #004d40; background-color: #e0f7fa; } QGroupBox::title { padding: 5px; }"
        style_disabled = "QGroupBox { font-weight: bold; color: #888888; background-color: #e8ecef; } QGroupBox::title { padding: 5px; }"
        style = style_enabled if enabled else style_disabled
        for group in [self.input_group, self.action_group, self.keyword_group, self.comment_group, self.output_group]:
            group.setStyleSheet(style)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel("YouTube Spam Cleaner")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #00695c;")
        main_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        login_group = QGroupBox("Step 1: Login")
        login_group.setStyleSheet("QGroupBox { font-weight: bold; color: #004d40; background-color: #e0f7fa; } QGroupBox::title { padding: 5px; }")
        login_layout = QVBoxLayout()
        self.login_btn = QPushButton("Login with Google")
        self.login_btn.setStyleSheet("background-color: #009688; color: white; padding: 8px; font-weight: bold;")
        self.login_btn.clicked.connect(self.login_clicked)
        login_layout.addWidget(self.login_btn)
        login_group.setLayout(login_layout)
        main_layout.addWidget(login_group)

        self.input_group = QGroupBox("Input")
        input_layout = QVBoxLayout()
        input_type_layout = QHBoxLayout()
        self.video_id_radio = QRadioButton("Video ID")
        self.channel_id_radio = QRadioButton("Channel ID")
        self.video_id_radio.setChecked(True)
        self.video_id_radio.toggled.connect(self.update_input_label)
        self.channel_id_radio.toggled.connect(self.update_input_label)
        input_type_layout.addWidget(self.video_id_radio)
        input_type_layout.addWidget(self.channel_id_radio)
        self.input_label = QLabel("Video ID")
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter Video ID")
        input_layout.addLayout(input_type_layout)
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_field)
        self.input_group.setLayout(input_layout)
        main_layout.addWidget(self.input_group)

        self.action_group = QGroupBox("Action")
        action_layout = QVBoxLayout()
        self.delete_only = QRadioButton("Delete only")
        self.delete_ban = QRadioButton("Delete and Ban user")
        self.delete_only.setChecked(True)
        action_layout.addWidget(self.delete_only)
        action_layout.addWidget(self.delete_ban)
        self.action_group.setLayout(action_layout)
        main_layout.addWidget(self.action_group)

        self.keyword_group = QGroupBox("Spam Keywords")
        keyword_layout = QVBoxLayout()
        self.keyword_list = QListWidget()
        self.keyword_list.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc;")
        keyword_layout.addWidget(self.keyword_list)
        keyword_btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_keyword)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_keyword)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self.edit_keyword)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_keywords_clicked)
        for btn in [add_btn, remove_btn, edit_btn, save_btn]:
            btn.setStyleSheet("background-color: #81d4fa; color: #01579b; padding: 6px;")
        keyword_btn_layout.addWidget(add_btn)
        keyword_btn_layout.addWidget(remove_btn)
        keyword_btn_layout.addWidget(edit_btn)
        keyword_btn_layout.addWidget(save_btn)
        keyword_layout.addLayout(keyword_btn_layout)
        self.keyword_group.setLayout(keyword_layout)
        main_layout.addWidget(self.keyword_group)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 2px solid #004d40; background-color: #e0f7fa; }
            QTabBar::tab {
                background: #b2dfdb;
                color: #004d40;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border: 2px solid #004d40;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #00695c;
                color: white;
            }
            QTabBar::tab:!selected {
                background: #b2dfdb;
            }
        """)
        main_layout.addWidget(self.tab_widget)

        self.comment_group = QGroupBox("Comments (Check to select)")
        comment_layout = QVBoxLayout()
        self.comment_list = QListWidget()
        self.comment_list.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc; font-size: 14px;")
        self.comment_list.setMinimumHeight(200)
        comment_layout.addWidget(self.comment_list)
        button_layout = QHBoxLayout()
        self.list_btn = QPushButton("List Comments")
        self.list_btn.setStyleSheet("background-color: #009688; color: white; padding: 8px; font-weight: bold;")
        self.list_btn.clicked.connect(self.list_comments)
        self.process_selected_btn = QPushButton("Process Selected Comments")
        self.process_selected_btn.setStyleSheet("background-color: #009688; color: white; padding: 8px; font-weight: bold;")
        self.process_selected_btn.clicked.connect(self.process_selected_comments)
        button_layout.addWidget(self.list_btn)
        button_layout.addWidget(self.process_selected_btn)
        comment_layout.addLayout(button_layout)
        self.comment_group.setLayout(comment_layout)
        self.tab_widget.addTab(self.comment_group, "Comments")

        self.auto_group = QGroupBox("Auto-Process")
        auto_layout = QVBoxLayout()
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setSuffix(" minutes")
        self.interval_spin.setValue(5)
        self.process_btn = QPushButton("Start Auto-Process")
        self.process_btn.setStyleSheet("background-color: #009688; color: white; padding: 8px; font-weight: bold;")
        self.process_btn.clicked.connect(self.toggle_auto_process)
        auto_layout.addWidget(QLabel("Interval for recurring auto-process:"))
        auto_layout.addWidget(self.interval_spin)
        auto_layout.addWidget(self.process_btn)
        auto_layout.addStretch()
        self.auto_group.setLayout(auto_layout)
        self.tab_widget.addTab(self.auto_group, "Auto")

        self.output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        self.hide_output_cb = QCheckBox("Hide Output")
        self.hide_output_cb.setStyleSheet("color: #004d40;")
        self.hide_output_cb.stateChanged.connect(self.toggle_output)
        output_layout.addWidget(self.hide_output_cb)
        self.output_text = QTextEdit()
        self.output_text.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc;")
        self.output_text.setReadOnly(True)
        clear_btn = QPushButton("Clear Output")
        clear_btn.setStyleSheet("background-color: #81d4fa; color: #01579b; padding: 6px;")
        clear_btn.clicked.connect(self.clear_output)
        output_layout.addWidget(self.output_text)
        output_layout.addWidget(clear_btn)
        self.output_group.setLayout(output_layout)
        main_layout.addWidget(self.output_group)

    def toggle_auto_process(self):
        if self.is_scheduled:
            if self.timer:
                self.timer.stop()
                self.timer = None
            self.process_btn.setText("Start Auto-Process")
            self.is_scheduled = False
            self.output_text.append("Auto-process stopped.")
            self.set_sections_enabled(True)
            self.login_btn.setEnabled(True)
        else:
            if not service:
                QMessageBox.warning(self, "Warning", "Please login first.")
                self.output_text.append("Error: Please login first.")
                return
            video_id = self.input_field.text().strip() if self.video_id_radio.isChecked() else None
            channel_id = self.input_field.text().strip() if self.channel_id_radio.isChecked() else None
            if not video_id and not channel_id:
                QMessageBox.warning(self, "Warning", "Please enter a Video ID or Channel ID.")
                self.output_text.append("Error: Please enter a Video ID or Channel ID.")
                return
            self.set_sections_enabled(False)
            self.login_btn.setEnabled(False)
            self.auto_group.setEnabled(True)
            self.process_btn.setEnabled(True)
            self.output_group.setEnabled(True)
            self.auto_group.setStyleSheet("QGroupBox { font-weight: bold; color: #004d40; background-color: #e0f7fa; } QGroupBox::title { padding: 5px; }")
            interval_min = self.interval_spin.value()
            interval_ms = interval_min * 60 * 1000
            self.timer = QTimer()
            self.timer.timeout.connect(self.delete_or_ban_comments)
            self.timer.start(interval_ms)
            self.output_text.append(f"Started auto-process every {interval_min} minutes.")
            self.process_btn.setText("Stop Auto-Process")
            self.is_scheduled = True

    def update_input_label(self):
        if self.video_id_radio.isChecked():
            self.input_label.setText("Video ID")
            self.input_field.setPlaceholderText("Enter Video ID")
        else:
            self.input_label.setText("Channel ID")
            self.input_field.setPlaceholderText("Enter Channel ID")
        self.input_field.clear()

    def toggle_output(self, state):
        self.output_text.setVisible(state == Qt.CheckState.Unchecked.value)
        self.output_group.findChild(QPushButton, "").setVisible(state == Qt.CheckState.Unchecked.value)

    def login_clicked(self):
        self.output_text.clear()
        if login():
            self.set_sections_enabled(True)
            self.output_text.append("Login successful. Ready to list or process comments.")

    def update_keyword_list(self):
        self.keyword_list.clear()
        for word in spam_keywords:
            self.keyword_list.addItem(word)

    def add_keyword(self):
        word, ok = QInputDialog.getText(self, "Add Keyword", "Enter a spam keyword:")
        if ok and word and word not in spam_keywords:
            spam_keywords.append(word)
            self.update_keyword_list()
            self.output_text.append(f"Added keyword: {word}")

    def remove_keyword(self):
        selected = self.keyword_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select a keyword to remove.")
            return
        word = selected.text()
        spam_keywords.remove(word)
        self.update_keyword_list()
        self.output_text.append(f"Removed keyword: {word}")

    def edit_keyword(self):
        selected = self.keyword_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select a keyword to edit.")
            return
        old_word = selected.text()
        new_word, ok = QInputDialog.getText(self, "Edit Keyword", "Edit the keyword:", text=old_word)
        if ok and new_word and new_word != old_word:
            spam_keywords[spam_keywords.index(old_word)] = new_word
            self.update_keyword_list()
            self.output_text.append(f"Edited keyword: {old_word} -> {new_word}")

    def save_keywords_clicked(self):
        save_keywords(spam_keywords, self.keyword_list)
        self.output_text.append("Spam keywords saved.")

    def list_comments(self):
        global selected_comments
        self.output_text.clear()
        self.comment_list.clear()
        selected_comments.clear()
        self.output_text.append(f"Using keywords: {', '.join(spam_keywords) if spam_keywords else 'None'}")
        self.output_text.append("Fetching comments...")

        video_id = None
        channel_id = None
        if self.video_id_radio.isChecked():
            video_id = self.input_field.text().strip() or None
        else:
            channel_id = self.input_field.text().strip() or None
        comments, error = get_comment_threads(video_id, channel_id)
        if error:
            QMessageBox.warning(self, "Warning", error)
            self.output_text.append(f"Error: {error}")
            return

        if not comments:
            self.output_text.append("No comments found.")
            return

        self.output_text.append(f"Found {len(comments)} comments:")
        for item in comments:
            comment = item["snippet"]["topLevelComment"]["snippet"]
            text = comment["textDisplay"]
            author = comment["authorDisplayName"]
            comment_id = item["snippet"]["topLevelComment"]["id"]
            matched_keywords = [word for word in spam_keywords if word.lower() in text.lower()]
            is_spam = bool(matched_keywords)
            status = f"SPAM (Matched: {', '.join(matched_keywords)})" if is_spam else "OK"

            self.output_text.append(f"{author}: {text} [{status}]")
            item_widget = QListWidgetItem(f"{author}: {text[:50]}... [{status}]")
            item_widget.setFlags(item_widget.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item_widget.setCheckState(Qt.CheckState.Checked if is_spam else Qt.CheckState.Unchecked)
            self.comment_list.addItem(item_widget)
            selected_comments.append((comment_id, item_widget))

    def process_selected_comments(self):
        self.output_text.clear()
        self.output_text.append("Processing selected comments...")
        if not service:
            QMessageBox.warning(self, "Warning", "Please login first.")
            self.output_text.append("Error: Please login first.")
            return
        if not selected_comments:
            QMessageBox.warning(self, "Warning", "No comments listed. Please list comments first.")
            self.output_text.append("Error: No comments listed.")
            return

        action = "delete" if self.delete_only.isChecked() else "ban"
        count = 0
        for comment_id, item_widget in selected_comments:
            if item_widget.checkState() == Qt.CheckState.Checked:
                try:
                    if action == "delete":
                        service.comments().delete(id=comment_id).execute()
                        self.output_text.append(f"Deleted comment (ID: {comment_id})")
                    elif action == "ban":
                        service.comments().setModerationStatus(
                            id=comment_id,
                            moderationStatus="rejected",
                            banAuthor=True
                        ).execute()
                        self.output_text.append(f"Banned user and deleted comment (ID: {comment_id})")
                    count += 1
                    time.sleep(0.5)
                except Exception as e:
                    self.output_text.append(f"Error processing comment {comment_id}: {e}")
        self.output_text.append(f"\nDone: {count} comments processed ({action}).")
        QMessageBox.information(self, "Done", f"{count} comments processed ({action}).")

    def delete_or_ban_comments(self):
        self.output_text.clear()
        self.output_text.append(f"Using keywords: {', '.join(spam_keywords) if spam_keywords else 'None'}")
        self.output_text.append("Processing auto-detected spam comments...")
        video_id = None
        channel_id = None
        if self.video_id_radio.isChecked():
            video_id = self.input_field.text().strip() or None
        else:
            channel_id = self.input_field.text().strip() or None
        comments, error = get_comment_threads(video_id, channel_id)
        if error:
            self.output_text.append(f"Error: {error}")
            return

        action = "delete" if self.delete_only.isChecked() else "ban"
        count = 0
        for item in comments:
            comment_snip = item["snippet"]["topLevelComment"]["snippet"]
            text = comment_snip["textDisplay"]
            comment_id = item["snippet"]["topLevelComment"]["id"]
            matched_keywords = [word for word in spam_keywords if word.lower() in text.lower()]
            if matched_keywords:
                try:
                    if action == "delete":
                        service.comments().delete(id=comment_id).execute()
                        self.output_text.append(f"Deleted comment (ID: {comment_id})")
                    elif action == "ban":
                        service.comments().setModerationStatus(
                            id=comment_id,
                            moderationStatus="rejected",
                            banAuthor=True
                        ).execute()
                        self.output_text.append(f"Banned user and deleted comment (ID: {comment_id})")
                    count += 1
                    time.sleep(0.5)
                except Exception as e:
                    self.output_text.append(f"Error processing comment {comment_id}: {e}")
        self.output_text.append(f"\nDone: {count} spam comments processed ({action}).")

    def clear_output(self):
        self.output_text.clear()
        self.output_text.append("Output cleared.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget { font-family: 'Segoe UI'; font-size: 12px; background-color: #e0f7fa; }")
    window = YouTubeSpamCleaner()
    window.show()
    sys.exit(app.exec())