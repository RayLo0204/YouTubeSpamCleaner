import os
from PyQt6.QtWidgets import QMessageBox

spam_keywords = []
spam_file = "spam_keywords.txt"

def load_keywords():
    global spam_keywords
    if os.path.exists(spam_file):
        with open(spam_file, "r", encoding="utf-8") as f:
            spam_keywords = [line.strip() for line in f if line.strip()]
    return spam_keywords

def save_keywords(keywords, list_widget=None):
    with open(spam_file, "w", encoding="utf-8") as f:
        for word in keywords:
            f.write(word + "\n")
    if list_widget:
        list_widget.clear()
        for word in keywords:
            list_widget.addItem(word)
    QMessageBox.information(None, "Saved", "Spam keywords saved successfully.")