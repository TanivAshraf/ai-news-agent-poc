    # app.py (This will be the main file name for our script)

import os
import requests
import feedparser # New library for RSS
import google.generativeai as genai
from datetime import datetime, timedelta
import re # For regular expressions to handle keywords

# --- Configuration (Get these from your environment variables later) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Still include for future/basic use

# Configure Google Gemini (will be used lightly for this PoC)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro') # Still define, but use sparingly for PoC

# --- Specific RSS Feeds for your PoC Sources ---
RSS_FEEDS = [
    {"name": "Globe and Mail - Business", "url": "https://www.theglobeandmail.com/business/feed/"},
    {"name": "Toronto Star - Business", "url": "https://www.thestar.com/business/feed/"},
    {"name": "National Observer", "url": "https://www.nationalobserver.com/rss"},
    {"name": "Financial Post", "url": "https://financialpost.com/feed/"},
    {"name": "Ontario Newsroom", "url": "https://news.ontario.ca/en/feed"},
    {"name": "The Hub", "url": "https://thehub.ca/feed/"},
    {"name": "The Logic", "url": "https://thelogic.co/feed/"},
    # Add other RSS feeds here if you find them
]

# --- Keywords for Filtering (Case-insensitive) ---
KEYWORDS = [
    "Energy", "clean energy", "clean economy", "mining", "critical minerals", "EV’s",
    "electric vehicles", "battery supply chain", "electrification", "generation",
    "transmission", "battery storage", "cement", "steel", "emissions", "decarbonization",
    "industrial strategy", "clean tech", "nuclear", "wind energy", "solar", "renewables",
    "natural gas", "oil and gas", "hydrogen", "investment tax credits", "clean tax credits",
    "EV rebates"
]
# Create a regex pattern for efficient case-insensitive keyword matching
KEYWORD_PATTERN = re.compile(r'\b(?:' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b', re.IGNORECASE)

def fetch_articles_from_rss():
    """Fetches articles from the configured RSS feeds."""
    all_articles = []
    print("Fetching articles from RSS feeds...")
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries:
                title = entry.title if hasattr(entry, 'title') else 'No Title'
                link = entry.link if hasattr(entry, 'link') else '#'
                summary = entry.summary if hasattr(entry, 'summary') else (entry.description if hasattr(entry, 'description') else 'No summary available.')
                
                # Basic keyword filtering for PoC
                if KEYWORD_PATTERN.search(title) or KEYWORD_PATTERN.search(summary):
                    all_articles.append({
                        "source": feed_info["name"],
                        "title": title,
                        "url": link,
                        "description": summary,
                        "published_date": entry.published if hasattr(entry, 'published') else 'N/A'
                    })
        except Exception as e:
            print(f"Error fetching RSS for {feed_info['name']} ({feed_info['url']}): {e}")
    print(f"Found {len(all_articles)} articles from RSS feeds after initial keyword filter.")
    return all_articles

def fetch_articles_from_newsapi(query="Canada clean energy", days_back=1, language="en", max_articles=10):
    """Fetches articles from News API for a given query (as a supplementary source)."""
    if not NEWS_API_KEY:
        print("NEWS_API_KEY is not set, skipping News API fetch.")
        return []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    # Combine general Canada query with keywords for NewsAPI
    newsapi_query = f"({query}) AND ({' OR '.join(KEYWORDS)})"

    url = f"https://newsapi.org/v2/everything"
    params = {
        "q": newsapi_query,
        "language": language,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "sortBy": "relevancy",
        "pageSize": max_articles,
        "apiKey": NEWS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok':
            # News API already filters by keywords in the query, so just format
            formatted_articles = []
            for article in data['articles']:
                formatted_articles.append({
                    "source": article.get('source', {}).get('name', 'News API'),
                    "title": article.get('title', 'No Title'),
                    "url": article.get('url', '#'),
                    "description": article.get('description', 'No description available.'),
                    "published_date": article.get('publishedAt', 'N/A')
                })
            print(f"Found {len(formatted_articles)} articles from News API.")
            return formatted_articles
        else:
            print(f"News API Error: {data.get('message', 'Unknown error')}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from News API: {e}")
        return []

def filter_and_present_articles(all_articles):
    """Formats the aggregated articles for display."""
    
    if not all_articles:
        return "No relevant articles found today for your specified sources and keywords."

    output = ["<h2>Custom News Aggregator Briefing</h2>", "<hr>"]
    output.append(f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>")
    output.append("<p><strong>Filtering Keywords:</strong> " + ", ".join(KEYWORDS) + "</p>")
    output.append("<hr>")

    # Deduplicate articles based on URL to avoid showing the same article from different feeds/APIs
    unique_articles = {article['url']: article for article in all_articles}.values()
    
    # Sort by published date (most recent first)
    sorted_articles = sorted(
        unique_articles, 
        key=lambda x: datetime.strptime(x['published_date'], '%Y-%m-%dT%H:%M:%SZ') if 'T' in x['published_date'] and 'Z' in x['published_date'] else datetime.min, 
        reverse=True
    )
    
    for article in sorted_articles:
        output.append(f"<h3><a href='{article['url']}' target='_blank'>{article['title']}</a></h3>")
        output.append(f"<p><strong>Source:</strong> {article['source']} | <strong>Published:</strong> {article['published_date']}</p>")
        output.append(f"<p>{article['description']}</p>")
        output.append("<hr>")
    
    return "\n".join(output)

def handler(request):
    """
    This is the entry point for our Vercel serverless function.
    It will be triggered and run the news gathering and aggregation.
    """
    try:
        print("Starting news aggregation PoC...")
        
        # Fetch from RSS feeds (primary sources)
        rss_articles = fetch_articles_from_rss()

        # Fetch from News API as a supplement or for sources not in RSS
        # For this PoC, we'll keep the News API query broad for Canada & keywords
        # and let deduplication handle overlaps.
        newsapi_articles = fetch_articles_from_newsapi() 
        
        # Combine and present
        all_fetched_articles = rss_articles + newsapi_articles
        briefing_html = filter_and_present_articles(all_fetched_articles)
        
        print("Aggregated briefing generated successfully.")
        
        # Vercel function will display this HTML content directly.
        return briefing_html
    except Exception as e:
        print(f"An unexpected error occurred in handler: {e}")
        return f"<h1>An error occurred:</h1><p>{e}</p><p>Check Vercel logs for more details.</p>"

# If you want to test locally (optional, for developers)
if __name__ == "__main__":
    # For local testing, ensure NEWS_API_KEY and GEMINI_API_KEY are set in your environment
    # or replace os.environ.get with your actual keys for quick testing (NOT for production)
    # os.environ["NEWS_API_KEY"] = "YOUR_NEWS_API_KEY"
    # os.environ["GEMINI_API_KEY"] = "YOUR_GEMINI_API_KEY" # Not strictly needed for this PoC but good practice
    
    # Simulate a request
    print(handler(None))
