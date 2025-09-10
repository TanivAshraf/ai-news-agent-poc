# app.py

import os
import requests
import feedparser
import google.generativeai as genai
from datetime import datetime, timedelta
import re
from supabase import create_client, Client # New import

# --- Configuration (Get these from your environment variables) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Still included for future/basic use
SUPABASE_URL = os.environ.get("SUPABASE_URL") # New
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # New (service_role key)

# Configure Google Gemini (will be used lightly for this PoC)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Specific RSS Feeds for your PoC Sources ---
RSS_FEEDS = [
    {"name": "Globe and Mail - Business", "url": "https://www.theglobeandmail.com/business/feed/"},
    {"name": "Toronto Star - Business", "url": "https://www.thestar.com/business/feed/"},
    {"name": "National Observer", "url": "https://www.nationalobserver.com/rss"},
    {"name": "Financial Post", "url": "https://financialpost.com/feed/"},
    {"name": "Ontario Newsroom", "url": "https://news.ontario.ca/en/feed"},
    {"name": "The Hub", "url": "https://thehub.ca/feed/"},
    {"name": "The Logic", "url": "https://thelogic.co/feed/"},
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
                
                matched_keywords = [k for k in KEYWORDS if re.search(r'\b' + re.escape(k) + r'\b', title + ' ' + summary, re.IGNORECASE)]

                if matched_keywords: # Only add if keywords are found
                    all_articles.append({
                        "source": feed_info["name"],
                        "title": title,
                        "url": link,
                        "description": summary,
                        "published_date": entry.published if hasattr(entry, 'published') else 'N/A',
                        "keywords_matched": matched_keywords
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
            formatted_articles = []
            for article in data['articles']:
                title = article.get('title', 'No Title')
                description = article.get('description', 'No description available.')
                matched_keywords = [k for k in KEYWORDS if re.search(r'\b' + re.escape(k) + r'\b', title + ' ' + description, re.IGNORECASE)]

                if matched_keywords: # Only add if keywords are found
                    formatted_articles.append({
                        "source": article.get('source', {}).get('name', 'News API'),
                        "title": title,
                        "url": article.get('url', '#'),
                        "description": description,
                        "published_date": article.get('publishedAt', 'N/A'),
                        "keywords_matched": matched_keywords
                    })
            print(f"Found {len(formatted_articles)} articles from News API.")
            return formatted_articles
        else:
            print(f"News API Error: {data.get('message', 'Unknown error')}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from News API: {e}")
        return []

def store_articles_in_supabase(all_articles):
    """Stores unique aggregated articles into Supabase."""
    if not all_articles:
        print("No articles to store.")
        return "No articles processed."

    # Deduplicate articles based on URL
    unique_articles = {article['url']: article for article in all_articles}.values()
    articles_to_insert = []

    print(f"Attempting to insert {len(unique_articles)} unique articles into Supabase.")

    for article in unique_articles:
        # Format published_date for Supabase timestamp type
        pub_date = article['published_date']
        try:
            # Handle various date formats if necessary, standardizing to ISO 8601
            if 'T' in pub_date and 'Z' in pub_date: # News API format
                formatted_date = datetime.strptime(pub_date, '%Y-%m-%dT%H:%M:%SZ').isoformat() + 'Z'
            else: # RSS may have other formats, try a generic parse
                formatted_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %z').isoformat() # Example for RFC 822
        except ValueError:
            try: # Fallback for simpler RSS date formats
                formatted_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z').isoformat()
            except ValueError:
                formatted_date = None # Set to None if parsing fails


        articles_to_insert.append({
            "source": article.get('source'),
            "title": article.get('title'),
            "url": article.get('url'),
            "description": article.get('description'),
            "published_date": formatted_date,
            "keywords_matched": article.get('keywords_matched', [])
        })

    # Insert in batches if many articles (Supabase client handles this by default for small amounts)
    if articles_to_insert:
        try:
            # The 'upsert' method handles inserting new records and updating existing ones (based on unique constraints like 'url')
            response = supabase.table('articles').upsert(articles_to_insert, on_conflict='url').execute()
            print(f"Supabase upsert response: {response.data}")
            return f"Successfully processed {len(response.data)} articles to Supabase."
        except Exception as e:
            print(f"Error inserting into Supabase: {e}")
            return f"Error storing articles: {e}"
    else:
        return "No unique articles to store in Supabase after deduplication."


def handler(request):
    """
    This is the entry point for our GitHub Actions script.
    It runs the news gathering and aggregation and stores data in Supabase.
    """
    try:
        print("Starting news aggregation PoC (Supabase backend)...")
        
        # Fetch from RSS feeds (primary sources)
        rss_articles = fetch_articles_from_rss()

        # Fetch from News API as a supplement
        newsapi_articles = fetch_articles_from_newsapi() 
        
        # Combine all fetched articles
        all_fetched_articles = rss_articles + newsapi_articles
        
        # Store them in Supabase
        result_message = store_articles_in_supabase(all_fetched_articles)
        
        print(f"Aggregation complete: {result_message}")
        return result_message # This will be visible in GitHub Actions logs
    except Exception as e:
        print(f"An unexpected error occurred in handler: {e}")
        return f"An error occurred: {e}"

# If you want to test locally (optional, for developers)
if __name__ == "__main__":
    # For local testing, ensure NEWS_API_KEY, GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY
    # are set in your environment variables, or hardcode them temporarily for testing (NOT for production)
    # os.environ["NEWS_API_KEY"] = "YOUR_NEWS_API_KEY"
    # os.environ["GEMINI_API_KEY"] = "YOUR_GEMINI_API_KEY"
    # os.environ["SUPABASE_URL"] = "YOUR_SUPABASE_URL"
    # os.environ["SUPABASE_KEY"] = "YOUR_SUPABASE_SERVICE_ROLE_KEY"
    print(handler(None))
