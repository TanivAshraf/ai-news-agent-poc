// script.js

// Initialize Supabase client with your project details
// IMPORTANT: For a production application, these keys should ideally be loaded
// from environment variables via a build step (e.g., using a framework like Next.js).
// For this static HTML/JS PoC, directly embedding the public anon key is common,
// but be aware of the security implications for highly sensitive data in a public repo.
const SUPABASE_URL = "https://zdcliufkeprmrkxmqifr.supabase.co"; // YOUR_SUPABASE_URL
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkY2xpdWZrZXBybXJreG1xaWZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2Njg0OTEsImV4cCI6MjA3MTI0NDQ5MX0.M8I8qk-oh8H3tZ8-KWHXfoN_p5jhdfRq-4j0OEbiO_s"; // YOUR_SUPABASE_ANON_KEY

// --- THIS LINE HAS BEEN CORRECTED ---
// We explicitly use window.supabase to refer to the global object from the CDN script.
const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);


const newsContainer = document.getElementById('news-container');
const briefingContainer = document.getElementById('briefing-content');
const sortOrderSelect = document.getElementById('sortOrder');

async function fetchDailyBriefing() {
    briefingContainer.innerHTML = '<p>Loading daily briefing...</p>';
    const today = new Date().toISOString().split('T')[0]; // Get today's date in YYYY-MM-DD format

    let { data: briefing, error } = await supabase
        .from('daily_briefings')
        .select('*')
        .eq('briefing_date', today) // Fetch today's briefing
        .single(); // Expecting only one briefing per day

    if (error && error.code !== 'PGRST116') { // PGRST116 means no rows found (which is fine if no briefing yet)
        console.error('Error fetching daily briefing:', error.message);
        briefingContainer.innerHTML = '<p>Failed to load daily briefing.</p>';
        return;
    }

    if (briefing) {
        renderBriefing(briefing);
    } else {
        briefingContainer.innerHTML = '<p>No AI briefing available for today yet. Check back later!</p>';
    }
}

function renderBriefing(briefing) {
    let briefingHtml = `<h3>${briefing.title || "AI Morning Briefing"}</h3>`;
    briefingHtml += `<p><strong>Executive Summary:</strong> ${briefing.summary_text || 'No summary available.'}</p>`;

    if (briefing.key_developments && briefing.key_developments.length > 0) {
        briefingHtml += `<h3>Key Developments:</h3><ul>`;
        briefing.key_developments.forEach(item => {
            briefingHtml += `<li>${item}</li>`;
        });
        briefingHtml += `</ul>`;
    }

    if (briefing.strategic_implications) {
        briefingHtml += `<h3>Strategic Implications for New Economy Canada:</h3><p>${briefing.strategic_implications}</p>`;
    }

    if (briefing.suggested_reactions) {
        briefingHtml += `<h3>Suggested Reactions:</h3><p>${briefing.suggested_reactions}</p>`;
    }

    if (briefing.related_article_urls && briefing.related_article_urls.length > 0) {
        briefingHtml += `<h3>Relevant Article URLs:</h3><ul>`;
        briefing.related_article_urls.forEach(url => {
            briefingHtml += `<li><a href="${url}" target="_blank">${url}</a></li>`;
        });
        briefingHtml += `</ul>`;
    }
    
    briefingContainer.innerHTML = briefingHtml;
}


async function fetchAndRenderAggregatedNews() {
    newsContainer.innerHTML = '<p>Loading news articles...</p>';
    let { data: articles, error } = await supabase
        .from('articles')
        .select('*'); 

    if (error) {
        console.error('Error fetching articles:', error.message);
        newsContainer.innerHTML = '<p>Failed to load news articles. Please try again later.</p>';
        return;
    }

    if (articles.length === 0) {
        newsContainer.innerHTML = '<p>No relevant news articles found today.</p>';
        return;
    }

    renderAggregatedNews(articles);
}

function renderAggregatedNews(articles) {
    const sortOrder = sortOrderSelect.value;
    let sortedArticles = [...articles]; 

    switch (sortOrder) {
        case 'published_date_asc':
            sortedArticles.sort((a, b) => {
                const dateA = a.published_date ? new Date(a.published_date) : new Date(0);
                const dateB = b.published_date ? new Date(b.published_date) : new Date(0);
                return dateA - dateB;
            });
            break;
        case 'published_date_desc':
            sortedArticles.sort((a, b) => {
                const dateA = a.published_date ? new Date(a.published_date) : new Date(0);
                const dateB = b.published_date ? new Date(b.published_date) : new Date(0);
                return dateB - dateA;
            });
            break;
        case 'source_asc':
            sortedArticles.sort((a, b) => (a.source || '').localeCompare(b.source || ''));
            break;
        default:
            break;
    }

    newsContainer.innerHTML = ''; 

    sortedArticles.forEach(article => {
        const articleDate = article.published_date ? new Date(article.published_date).toLocaleDateString(undefined, {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : 'N/A';

        const keywordsHtml = article.keywords_matched && article.keywords_matched.length > 0
            ? article.keywords_matched.map(keyword => `<span>${keyword}</span>`).join('')
            : '';

        const newsCard = `
            <div class="news-card">
                <h2><a href="${article.url}" target="_blank">${article.title}</a></h2>
                <p class="news-meta">
                    <span><strong>Source:</strong> ${article.source || 'Unknown'}</span>
                    <span><strong>Published:</strong> ${articleDate}</span>
                </p>
                <p class="news-description">${article.description || 'No description available.'}</p>
                <div class="news-keywords">${keywordsHtml}</div>
            </div>
        `;
        newsContainer.innerHTML += newsCard;
    });
}

// Event listener for sorting
sortOrderSelect.addEventListener('change', fetchAndRenderAggregatedNews);

// Initial fetches when the page loads
fetchDailyBriefing();
fetchAndRenderAggregatedNews();
