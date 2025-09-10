# backend/app.py

import os
import requests
import feedparser
import google.generativeai as genai
from datetime import datetime, timedelta, date
import re
from supabase import create_client, Client

# --- Configuration (Get these from your environment variables) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # service_role key

# --- Configure Google Gemini ---
def get_gemini_model():
    """
    Configures Google Gemini and finds a suitable model, prioritizing 'gemini-pro'.
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set. Cannot configure Gemini.")
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    
    available_models = list(genai.list_models())
    
    # Priority 1: Try 'gemini-pro'
    for m in available_models:
        if m.name == 'gemini-pro' and 'generateContent' in m.supported_generation_methods:
            print("Found suitable Gemini model: models/gemini-pro (preferred).")
            return genai.GenerativeModel('gemini-pro')
            
    # Priority 2: Fallback to 'gemini-1.5-pro' if 'gemini-pro' isn't available or suitable
    for m in available_models:
        if m.name == 'gemini-1.5-pro' and 'generateContent' in m.supported_generation_methods: # Note: 'gemini-1.5-pro-latest' often resolves to 'gemini-1.5-pro'
            print("Found suitable Gemini model: models/gemini-1.5-pro (fallback).")
            return genai.GenerativeModel('gemini-1.5-pro')

    print("No suitable Gemini model found that supports 'generateContent'. AI analysis will be skipped.")
    return None

model = get_gemini_model() # Initialize the model dynamically

print(f"DEBUG: Found {len(available_models)} models.")
for m in available_models:
    print(f"DEBUG: Model '{m.name}' supports: {m.supported_generation_methods}")

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

                if matched_keywords:
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

                if matched_keywords:
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
        print("No articles to store in 'articles' table.")
        return 0

    unique_articles = {article['url']: article for article in all_articles}.values()
    articles_to_insert = []

    for article in unique_articles:
        pub_date = article['published_date']
        formatted_date = None
        try:
            if 'T' in pub_date and 'Z' in pub_date: # ISO format from News API
                formatted_date = datetime.strptime(pub_date, '%Y-%m-%dT%H:%M:%SZ').isoformat() + 'Z'
            elif re.match(r'^\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}$', pub_date): # RFC 822 with +/- offset
                formatted_date = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %z').isoformat()
            elif re.match(r'^\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} \w{3}$', pub_date): # RFC 822 with timezone name
                pub_date_no_tz_name = re.sub(r' \w{3}$', ' +0000', pub_date) 
                try:
                    formatted_date = datetime.strptime(pub_date_no_tz_name, '%a, %d %b %Y %H:%M:%S %z').isoformat()
                except ValueError:
                    print(f"Warning: Failed to parse date '{pub_date}' after timezone name strip.")
                    formatted_date = None
            elif pub_date: # Try generic parsing for other non-empty formats
                try:
                    formatted_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00') if 'Z' in pub_date else pub_date).isoformat()
                except ValueError:
                    print(f"Warning: Generic parsing failed for date '{pub_date}'.")
                    formatted_date = None
            else: # pub_date is empty or None
                formatted_date = None
        except ValueError as e:
            print(f"Warning: Could not parse date '{pub_date}'. Error: {e}")
            formatted_date = None

        articles_to_insert.append({
            "source": article.get('source'),
            "title": article.get('title'),
            "url": article.get('url'),
            "description": article.get('description'),
            "published_date": formatted_date,
            "keywords_matched": article.get('keywords_matched', [])
        })

    if articles_to_insert:
        try:
            response = supabase.table('articles').upsert(articles_to_insert, on_conflict='url').execute()
            print(f"Successfully upserted {len(response.data)} articles into 'articles' table.")
            return len(response.data)
        except Exception as e:
            print(f"Error inserting into Supabase 'articles' table: {e}")
            return 0
    else:
        return 0

def analyze_and_brief_with_gemini(articles_for_analysis):
    """
    Uses Gemini to analyze articles and generate a consolidated daily briefing.
    """
    if not model: # Check if model was successfully initialized by get_gemini_model()
        print("Gemini model not initialized. Skipping AI analysis.")
        return None

    if not articles_for_analysis:
        print("No articles to analyze for the daily briefing.")
        return None

    # Construct the persona and task for Gemini
    persona = (
        "You are a senior political analyst for 'New Economy Canada'. "
        "Your raison d’etre is to ramp up awareness of and support for solutions "
        "and good things happening in the clean economy. "
        "You communicate the urgency for Canada to act now to remain relevant in the global economy. "
        "You are trying to accelerate the clean energy transition and make Canada a leader in this transition. "
        "You always look for concrete policy actions, investment trends, and potential challenges or 'greenwashing'. "
    )

    task_instruction = (
        "Based on the following news articles, generate a 'Morning Briefing' for today. "
        "Your output should be structured to help 'New Economy Canada' monitor, observe, and react to news, "
        "and understand the narrative being shaped. "
        "Prioritize quality and focus. Here's the structure I need:\n\n"
        "**Briefing Title:** AI Morning Briefing - [Today's Date]\n\n"
        "**Executive Summary:** A concise overview of the most critical developments (2-3 sentences).\n\n"
        "**Key Developments:**\n"
        "- [Bullet point 1: Major news item, e.g., 'Government announces X funding for Y project']\n"
        "- [Bullet point 2: Key policy shift, e.g., 'New provincial legislation on Z']\n"
        "- [Bullet point 3: Industry trends or notable investments, e.g., 'Company A invests in B technology']\n"
        "- ... (up to 5 bullet points)\n\n"
        "**Strategic Implications for New Economy Canada:** (Analyze potential impacts, what to watch for, narrative shaping elements)\n"
        "- [Implication 1]\n"
        "- [Implication 2]\n\n"
        "**Suggested Reactions:** (Based on the news, recommend positive or concerned tones)\n"
        "- **Positive:** [If supportive public policy, funding, etc., suggest an action/stance]\n"
        "- **Concerned:** [If harmful public policy, 'greenwashing', etc., suggest an action/stance]\n\n"
        "**Relevant Article URLs:**\n"
        "- [Link 1: Brief description]\n"
        "- [Link 2: Brief description]\n"
        "- ...\n\n"
        "Here are the articles for your analysis (focus on titles and descriptions):\n\n"
    )

    articles_text_for_ai = []
    related_urls = []
    for i, article in enumerate(articles_for_analysis):
        title = article.get('title', 'No Title')
        url = article.get('url', '#')
        description = article.get('description', 'No description available.')
        
        article_content = f"Title: {title}\nDescription: {description}\nURL: {url}"
        
        articles_text_for_ai.append(f"--- Article {i+1} ---\n{article_content}\n")
        related_urls.append(url)

    full_prompt = persona + "\n\n" + task_instruction + "\n".join(articles_text_for_ai)

    try:
        print(f"Sending articles to Gemini model '{model.model_name}' for analysis...")
        response = model.generate_content(full_prompt)
        briefing_text = response.text
        print("Gemini analysis complete.")
        
        briefing_data = parse_gemini_briefing(briefing_text, related_urls)
        briefing_data['raw_ai_response'] = briefing_text
        return briefing_data

    except Exception as e:
        print(f"Error generating content with Gemini: {e}")
        return {
            "title": f"AI Briefing Error - {date.today().strftime('%Y-%m-%d')}",
            "summary_text": f"Error during AI analysis: {e}. Raw AI response might be incomplete or empty.",
            "key_developments": [],
            "strategic_implications": "Could not perform full analysis due to AI error.",
            "suggested_reactions": "Monitor AI service status.",
            "related_article_urls": related_urls,
            "raw_ai_response": f"Error: {e}\nPrompt: {full_prompt}"
        }

def parse_gemini_briefing(briefing_text, related_urls):
    """Parses the structured text from Gemini into a dictionary."""
    parsed_data = {
        "title": "AI Morning Briefing - " + date.today().strftime('%Y-%m-%d'),
        "summary_text": "",
        "key_developments": [],
        "strategic_implications": "",
        "suggested_reactions": "",
        "related_article_urls": related_urls
    }

    sections = {
        "Briefing Title": r"^\*\*Briefing Title:\*\* (.*?)$",
        "Executive Summary": r"^\*\*Executive Summary:\*\*\s*(.*?)(?=\n\n\*\*Key Developments\*\*|$)",
        "Key Developments": r"^\*\*Key Developments:\*\*\s*(.*?)(?=\n\n\*\*Strategic Implications\*\*|$)",
        "Strategic Implications for New Economy Canada": r"^\*\*Strategic Implications for New Economy Canada:\*\*\s*(.*?)(?=\n\n\*\*Suggested Reactions\*\*|$)",
        "Suggested Reactions": r"^\*\*Suggested Reactions:\*\*\s*(.*?)(?=\n\n\*\*Relevant Article URLs\*\*|$)",
    }

    title_match = re.search(sections["Briefing Title"], briefing_text, re.MULTILINE)
    if title_match:
        parsed_data["title"] = title_match.group(1).strip()
    
    summary_match = re.search(sections["Executive Summary"], briefing_text, re.DOTALL | re.MULTILINE)
    if summary_match:
        parsed_data["summary_text"] = summary_match.group(1).strip()

    dev_match = re.search(sections["Key Developments"], briefing_text, re.DOTALL | re.MULTILINE)
    if dev_match:
        dev_text = dev_match.group(1)
        parsed_data["key_developments"] = [item.strip() for item in re.findall(r'^- (.+)$', dev_text, re.MULTILINE)]
    
    imp_match = re.search(sections["Strategic Implications for New Economy Canada"], briefing_text, re.DOTALL | re.MULTILINE)
    if imp_match:
        parsed_data["strategic_implications"] = imp_match.group(1).strip()

    react_match = re.search(sections["Suggested Reactions"], briefing_text, re.DOTALL | re.MULTILINE)
    if react_match:
        parsed_data["suggested_reactions"] = react_match.group(1).strip()

    return parsed_data

def store_briefing_in_supabase(briefing_data):
    """Stores the AI-generated briefing into the 'daily_briefings' table."""
    if not briefing_data:
        print("No briefing data to store.")
        return "No briefing processed."

    briefing_to_insert = {
        "briefing_date": date.today().isoformat(),
        "title": briefing_data.get("title"),
        "summary_text": briefing_data.get("summary_text"),
        "key_developments": briefing_data.get("key_developments"),
        "strategic_implications": briefing_data.get("strategic_implications"),
        "suggested_reactions": briefing_data.get("suggested_reactions"),
        "related_article_urls": briefing_data.get("related_article_urls"),
        "raw_ai_response": briefing_data.get("raw_ai_response")
    }

    try:
        response = supabase.table('daily_briefings').upsert(
            briefing_to_insert, 
            on_conflict='briefing_date'
        ).execute()
        
        print(f"Successfully stored/updated daily briefing in Supabase: {response.data}")
        return "Daily briefing stored successfully."
    except Exception as e:
        print(f"Error storing daily briefing in Supabase: {e}")
        return f"Error storing daily briefing: {e}"

def handler(request):
    """
    Main handler for the GitHub Actions workflow.
    Fetches news, stores individual articles, then generates and stores a daily briefing.
    """
    print("Starting AI News Agent (with Brain)...")
    
    rss_articles = fetch_articles_from_rss()
    newsapi_articles = fetch_articles_from_newsapi() 
    
    all_fetched_articles = rss_articles + newsapi_articles
    
    articles_stored_count = store_articles_in_supabase(all_fetched_articles)
    print(f"Stored {articles_stored_count} unique articles in 'articles' table.")

    # Only attempt AI analysis if the model was successfully initialized
    if model:
        briefing_data = analyze_and_brief_with_gemini(all_fetched_articles)
        briefing_result = store_briefing_in_supabase(briefing_data)
    else:
        # If model init failed, store an "error briefing"
        error_briefing = {
            "title": f"AI Briefing Initialization Error - {date.today().strftime('%Y-%m-%d')}",
            "summary_text": "Gemini model could not be initialized, likely due to API key issues or model unavailability. Please check backend logs.",
            "key_developments": [],
            "strategic_implications": "AI analysis skipped.",
            "suggested_reactions": "Check Gemini API key and model availability.",
            "related_article_urls": [a.get('url', '#') for a in all_fetched_articles],
            "raw_ai_response": "Model initialization failed."
        }
        briefing_result = store_briefing_in_supabase(error_briefing)
        print(f"Gemini model could not be initialized, skipping AI analysis. Briefing storage status: {briefing_result}")


    print(f"Full run complete. Briefing storage status: {briefing_result}")
    return f"AI Agent run completed. Articles: {articles_stored_count}, Briefing: {briefing_result}"

if __name__ == "__main__":
    print(handler(None))
