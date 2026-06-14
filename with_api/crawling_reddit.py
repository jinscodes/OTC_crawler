import praw

reddit = praw.Reddit(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    user_agent="mac:reddit-research:v1.0 (by /u/YOUR_USERNAME)"
)