# Luffy Bot - A One Piece Themed Discord Bot

![Luffy Bot](httpsd://i.imgur.com/example.png)  <!-- Replace with a real image of your bot -->

Luffy Bot is a feature-rich Discord bot inspired by the world of One Piece. It brings a pirate adventure to your Discord server, allowing users to become pirates, form crews, sail ships, and battle for supremacy.

## Features

- **🏴‍☠️ Pirate Profile:** Create your own pirate identity with a bounty and berry balance.
- **👥 Crew System:** Recruit members and form your own pirate crew.
- **🚢 Ship Management:** Own, upgrade, and customize your own pirate ship.
- **💰 Economy:** Earn "berries" through chat activity, daily claims, and voting.
- **⚔️ Duels & Ship Wars:** Challenge other pirates to duels and engage in epic ship battles.
- **🛒 Item Shop & Inventory:** Buy and sell items, including medical kits and repair tools.
- **옥션 Auction House:** Bid on or sell items and crew members in a player-driven market.
- **🎨 Cosmetics & Titles:** Customize your profile with unique titles and cosmetic items.
- **⬆️ Voting Rewards:** Get rewarded for voting for the bot on Top.gg.
- **🔥 Admin Commands:** Easy-to-use commands for server administration.

## Getting Started

Follow these instructions to get a local copy of the bot up and running for development and testing.

### Prerequisites

- Python 3.8 or higher
- A Firebase project for the database

### Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/luffy-cli.git
    cd luffy-cli
    ```

2.  **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

3.  **Set up your environment variables:**

    Create a `.env` file in the root of the project and add the following variables.

    ```env
    DISCORD_TOKEN=your_discord_bot_token
    TOPGG_AUTH_TOKEN=your_top.gg_webhook_authorization_token
    FIREBASE_CREDENTIALS_BASE64=your_base64_encoded_firebase_service_account_key
    ```

    - `DISCORD_TOKEN`: Your Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications).
    - `TOPGG_AUTH_TOKEN`: Your webhook authorization token from Top.gg (if you use it).
    - `FIREBASE_CREDENTIALS_BASE64`: Your Firebase service account key, encoded in base64. You can generate this by running the following command in your terminal:
      ```sh
      cat /path/to/your/firebase_key.json | base64 -w 0
      ```

### Running the Bot

Once you have completed the installation steps, you can start the bot with:

```sh
python bot.py
```

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".

1.  **Fork the Project**
2.  **Create your Feature Branch** (`git checkout -b feature/AmazingFeature`)
3.  **Commit your Changes** (`git commit -m 'Add some AmazingFeature'`)
4.  **Push to the Branch** (`git push origin feature/AmazingFeature`)
5.  **Open a Pull Request**

## License

Distributed under the MIT License. See `LICENSE` for more information.

*(You'll need to add a `LICENSE` file with the MIT License text if you choose to use it.)*
