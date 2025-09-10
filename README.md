# YouTube Spam Cleaner

-----

## English

This is a desktop application built with **PyQt6** and the **YouTube Data API v3** to help you manage and clean up spam comments on your YouTube videos or channel. It offers a powerful combination of manual review and automated processing, allowing you to delete comments or ban users based on a customizable list of keywords.

### Features

  - **Google Account Login**: Securely log in using your Google account with OAuth 2.0.
  - **Comment Retrieval**: Fetch and display comments from a specific video or your entire channel.
  - **Spam Detection**: Automatically flags comments containing your predefined keywords.
  - **Keyword Management**: Easily add, edit, remove, and save your list of spam keywords.
  - **Manual Processing**: Manually review and process flagged comments by choosing to delete them or ban the users.
  - **Auto-Process Mode**: Set a recurring timer to automatically process new comments based on your keyword list, without manual intervention.
  - **Real-time Logging**: View a detailed log of all actions performed by the application.

### Detailed Usage Guide

1.  **Login**: Click the **"Login with Google"** button and follow the on-screen instructions to select your `client_secret.json` file and authenticate.
2.  **Input Video/Channel ID**: Choose either **"Video ID"** or **"Channel ID"** and enter the corresponding ID into the text field.
3.  **Manage Keywords**: Use the **"Add"**, **"Remove"**, and **"Edit"** buttons to manage your spam keyword list. Click **"Save"** to save your changes to the `spam_keywords.txt` file.
4.  **List Comments**: Click **"List Comments"** to fetch and display comments. The application will automatically check comments that contain your spam keywords.
5.  **Process Comments**: In the **"Comments"** tab, review the listed comments, manually check or uncheck any comments you wish to, and then select your desired action: **"Delete only"** or **"Delete and Ban user."** Click **"Process Selected Comments"** to perform the chosen action.
6.  **Auto-Process**: Switch to the **"Auto"** tab, set the desired interval in minutes, and click **"Start Auto-Process."** The application will then automatically run at the specified interval.

### Prerequisites

Before running the application, you need to set up a Google Cloud project and enable the YouTube Data API.

1.  **Create a Google Cloud Project**: Go to the Google Cloud Console and create a new project.
2.  **Enable the YouTube Data API v3**: In the Google Cloud Console, navigate to the **APIs & Services** dashboard and enable the **YouTube Data API v3**.
3.  **Create OAuth 2.0 Credentials**: Go to the **Credentials** page, click **CREATE CREDENTIALS**, and select **OAuth client ID**. Choose "Desktop app" as the application type.
4.  **Download `client_secret.json`**: Download the `client_secret.json` file. You will need this file to log in to the application.

### Installation and Usage

1.  **Clone the Repository**:

    ```bash
    git clone https://github.com/<username>/<repo-name>.git
    cd <repo-name>
    ```

2.  **Install Dependencies**:
    You must have Python 3 installed. Install the required libraries using pip.

    ```bash
    pip install PyQt6 google-api-python-client google-auth-oauthlib
    ```

3.  **Run the Application**:
    Place your downloaded `client_secret.json` file in the same directory as the application script. Then, run the application from your terminal.

    ```bash
    python main.py
    ```

-----

## 繁體中文 (Traditional Chinese)

這是一款使用 **PyQt6** 和 **YouTube Data API v3** 開發的桌面應用程式，旨在幫助您管理和清理 YouTube 影片或頻道上的垃圾留言。它結合了手動審核與自動化處理的強大功能，讓您可以根據自訂的關鍵字列表來刪除留言或封鎖使用者。

### 功能特色

  - **Google 帳號登入：** 使用 OAuth 2.0 安全地透過您的 Google 帳號登入。
  - **留言檢索：** 擷取並顯示特定影片或整個頻道上的留言。
  - **垃圾留言偵測：** 自動標記包含您預設關鍵字的留言。
  - **關鍵字管理：** 輕鬆新增、編輯、移除及儲存您的垃圾關鍵字列表。
  - **手動處理模式：** 手動審核被標記的留言，選擇將其刪除或封鎖使用者。
  - **自動處理模式：** 設定定時器，根據您的關鍵字列表自動處理新的留言，無需手動干預。
  - **即時日誌：** 查看應用程式執行所有操作的詳細日誌。

### 詳細使用指南

1.  **登入：** 點擊「**Login with Google**」（使用 Google 登入）按鈕，並依照指示選擇您的 `client_secret.json` 檔案進行認證。
2.  **輸入影片/頻道 ID：** 選擇「**Video ID**」或「**Channel ID**」，然後在文字欄位中輸入對應的 ID。
3.  **管理關鍵字：** 使用「**Add**」（新增）、「**Remove**」（移除）和「**Edit**」（編輯）按鈕來管理您的垃圾關鍵字列表。點擊「**Save**」（儲存）將變更儲存到 `spam_keywords.txt` 檔案中。
4.  **列出留言：** 點擊「**List Comments**」（列出留言）以擷取並顯示留言。應用程式會自動勾選包含您設定的垃圾關鍵字的留言。
5.  **處理留言：** 在「**Comments**」標籤中，審核列出的留言，手動勾選或取消勾選您想處理的留言。然後選擇您希望執行的動作：「**Delete only**」（僅刪除）或「**Delete and Ban user**」（刪除並封鎖使用者）。最後，點擊「**Process Selected Comments**」（處理所選留言）即可執行所選動作。
6.  **自動處理：** 切換到「**Auto**」標籤，設定自動處理的間隔時間（分鐘），然後點擊「**Start Auto-Process**」（開始自動處理）。應用程式將會按照設定的間隔時間，自動執行處理程序。

### 前置作業

在執行應用程式之前，您需要設定一個 Google Cloud 專案並啟用 YouTube Data API。

1.  **建立 Google Cloud 專案：** 前往 Google Cloud Console 並建立一個新專案。
2.  **啟用 YouTube Data API v3：** 在 Google Cloud Console 中，導航至「**API 和服務**」儀表板，並啟用 **YouTube Data API v3**。
3.  **建立 OAuth 2.0 憑證：** 前往「**憑證**」頁面，點擊「**建立憑證**」，然後選擇「**OAuth 用戶端 ID**」。選擇「桌面應用程式」作為應用程式類型。
4.  **下載 `client_secret.json`：** 下載 `client_secret.json` 檔案。您將需要此檔案來登入應用程式。

### 安裝與使用方法

1.  **複製儲存庫：**

    ```bash
    git clone https://github.com/<username>/<repo-name>.git
    cd <repo-name>
    ```

2.  **安裝依賴套件：**
    您必須安裝 Python 3。使用 pip 安裝所需的函式庫。

    ```bash
    pip install PyQt6 google-api-python-client google-auth-oauthlib
    ```

3.  **執行應用程式：**
    將您下載的 `client_secret.json` 檔案放在與應用程式腳本相同的目錄中。然後，從您的終端機執行應用程式。

    ```bash
    python main.py
    ```
