---
name: generative-engine-optimization
description: When the user wants to optimize for AI search visibility (ChatGPT, Claude, Perplexity, AI Overviews). Also use when the user mentions "GEO," "AEO," "generative engine optimization," "AI search visibility," "LLM optimization," "GitHub GEO," "Grokipedia," "optimize for ChatGPT," "AI Overviews," "Bing Copilot," "Yandex AI," "Perplexity optimization," "GEO strategy," or "AI search optimization." For third-party publishing strategy (which platforms to use), use parasite-seo. For GitHub repos, README, and Awesome lists, use github. For Medium.com only, use medium-posts. For Grokipedia edits, use grokipedia-recommendations. For traditional Google SERP strategy, use seo-strategy.
metadata:
  version: 1.4.0
---

# Strategies: GEO (Generative Engine Optimization)

Guides GEO/AEO strategy for AI search visibility. GEO optimizes content for ChatGPT, Claude, Perplexity, and AI search summaries (Google AI Overviews, Bing Copilot, Yandex Search with AI)—getting cited in AI-generated answers rather than ranking in traditional SERPs. See **serp-features** for AI search as SERP features; **featured-snippet** for snippet optimization that overlaps with AI Overviews.

**When invoking**: On **first use**, if helpful, open with 1-2 sentences on what this skill covers and why it matters, then provide the main output. On **subsequent use** or when the user asks to skip, go directly to the main output.

## Scope

- **GEO** = Generative Engine Optimization
- **AEO** = Answer Engine Optimization
- **LLMO** = Large Language Model Optimization
- **AIO** = Artificial Intelligence Optimization

All refer to the same goal: visibility in AI assistant responses.

## GEO vs. SEO

| Dimension | SEO | GEO |
|-----------|-----|-----|
| **Goal** | Rankings in search results | Citations in AI answers |
| **User path** | Click → visit → convert | Answer in-place; may not visit |
| **Content** | Full page optimization | Clear, citable paragraphs |
| **Metrics** | Clicks, traffic | Citations, brand mentions |
| **Platforms** | Google, Bing, Yandex (organic) | AI Overviews, Copilot, Yandex AI, ChatGPT, Perplexity |

**Both matter**: Create content that ranks and gets cited. AI search summaries (AI Overviews, Copilot, Yandex AI) are **SERP features**—see **serp-features**. When SERP features cause **zero-click** (user gets answer without clicking), citation becomes the primary value; optimize for being cited, not just ranked.

## AI Search Platforms (SERP Features + Standalone)

| Platform | Type | Source Selection | Optimization Focus |
|----------|------|------------------|---------------------|
| **Google AI Overviews** | SERP feature | Top 10–12 organic; Gemini; favors older domains (49% over 15 yrs) | Traditional SEO; structured data; citable blocks |
| **Bing Copilot Search** | SERP feature | Bing index; GPT-4; 9.81% domain overlap with Google; favors younger domains (18.85%); LinkedIn signals for B2B | Bing optimization; LinkedIn presence; structured content |
| **Yandex Search with AI / Neuro** | SERP feature | Real-time Yandex search; YandexGPT; Russia-focused | Yandex indexing; Russian content; cited sources |
| **Perplexity** | Standalone | 200B+ URL index; independent crawl; favors recency, semantic alignment | Content freshness; semantic markup; mid-tier site opportunity |
| **ChatGPT (web search)** | Standalone | GPTbot; high-authority, frequently updated, LLM-friendly; favors older domains (45.8%) | Backlinks; structured data; authority signals |

**Citation behavior**: AI Overview citations 20–35% higher CTR than equivalent organic. Copilot: shortest responses, fewest links (~3.13/response). Perplexity: prominent URL citations, high trackability. [Geneo](https://geneo.app/blog/chatgpt-vs-perplexity-vs-google-ai-overview-geo-comparison/), [GEO AIO](https://geoaiomarketing.com/how-bing-copilot-selects-sources-compared-to-perplexity/)

**Platform traffic context**: Among standalone AI tools, ChatGPT captures ~60%+ of independent Gen AI traffic, Gemini ~20%+, while Claude, Perplexity, and Grok each account for ~2-4%+. These tools reach users directly. SERP features (AI Overviews, Copilot) reach users through existing search flows rather than as independent destinations. Prioritize optimization effort proportionally.

## How GEO Works (RAG & Search Supply)

GEO operates through **RAG (Retrieval-Augmented Generation)**—AI tools retrieve content first, then generate answers. The retrieval supply type varies by platform and determines which content surfaces for citation.

### Retrieval Supply Types

| Type | Description | Platforms |
|------|------------|-----------|
| **Self-built index** | Platform maintains its own crawl and search index | Perplexity (200B+ URL index, PerplexityBot); ChatGPT (OAI-SearchBot index) |
| **Bound search engine** | Platform uses a fixed first-party search API | Copilot (Bing); Google AI Overviews / AI Mode (Google Search + query fan-out) |
| **Third-party API** | Platform contracts a third-party search API | Claude for Government (Brave Search API); smaller AI tools using Tavily, Exa, You.com |
| **Hybrid** | Combination of self-built + external API | ChatGPT (OAI-SearchBot + possible search partners); Claude Web Search (supplier not publicly disclosed) |

### Platform Retrieval & Implications

| Platform | Primary Supply | Strategic Implication |
|----------|---------------|----------------------|
| **Google AI Overviews / AI Mode** | Google Search (query fan-out) | Strong traditional SEO + structured data is the most reliable path |
| **Bing Copilot** | Bing index | Requires Bing indexing; LinkedIn signals for B2B visibility |
| **ChatGPT (web search)** | OAI-SearchBot + partners | High-authority, frequently updated content favored; backlinks matter |
| **Perplexity** | Proprietary crawl | Content freshness; semantic alignment; mid-tier sites have opportunity |
| **Claude (web search)** | Not publicly disclosed | Focus on general crawlability and clear structured content |

**Third-party search APIs** (Tavily, Exa, You.com, Brave Search API) feed smaller AI tools and custom agents. Content that is crawlable and indexed via standard web search reaches these APIs through their supply indexes. **Core model training** (long, costly, not widely actionable): focus on RAG optimization.

## AI Crawlers & Discovery

AI crawlers fall into three categories with different implications for content strategy:

| Type | Purpose | Examples | Implication |
|------|---------|---------|-------------|
| **Training crawlers** | Gather data for model training | GPTBot, ClaudeBot, Google-Extended, Meta crawlers | Blocking via robots.txt prevents training data use; **does not** affect real-time search/retrieval by the same provider |
| **Index/RAG crawlers** | Build search index for retrieval | OAI-SearchBot, PerplexityBot, Claude-SearchBot, Bytespider (Cohere), AppleBot | **Must allow** for RAG-based AI citation; critical for GEO |
| **Real-time crawlers** | Fetch content on-demand at query time | ChatGPT-User (opt-in via web search) | Content must be accessible without a login; paywalls may block citation |

**Content discovery**: "Push" submissions for general web content are primarily supported through Bing IndexNow. Google's Indexing API is limited to JobPosting and BroadcastEvent pages only (not general content). OpenAI, Anthropic, Perplexity, xAI, Meta, and DeepSeek do **not** offer public submission portals—their crawlers discover content through standard crawl and sitemaps only.

AI crawlers generally do **not** execute JavaScript—critical content must be in initial HTML. See **rendering-strategies** for SSR, SSG, CSR; **site-crawlability** for AI crawler optimization; **robots-txt** for allow/block decisions. [Vercel/MERJ study](https://vercel.com/blog/the-rise-of-the-ai-crawler) (2024)

## Content Best Practices

| Practice | Purpose |
|----------|---------|
| **Direct-answer format** | Answer specific questions in clear paragraphs |
| **Entity signals** | Clear brand, product, author identity; see **entity-seo** |
| **Citable paragraphs** | Each block understandable on its own |
| **Distribution** | Website, **YouTube** (Google prioritizes YouTube in search; ~78% of social media citations in AI Overviews come from YouTube + Reddit), forums, Reddit—thoughtful comments can outrank blog posts |

### Article-Level GEO

For blog posts and articles, structure content for AI citation. Studies find content with TL;DR, structured formats, and clear answers is cited substantially more by AI engines.

| Element | Guideline |
|---------|-----------|
| **TL;DR or Key Takeaways** | Choose one: **TL;DR** = 50–100 word bold summary paragraph; **Key Takeaways** = 5–7 bullet points; placed after intro |
| **QAE pattern** | Question (H2) → Answer (2 sentences) → Evidence (data, examples, lists) |
| **Answer-first** | Direct answer in first 40–60 words after each H2 |
| **Answer blocks** | 100–200 words per section; direct answer + context + evidence + nuance |
| **Structured formats** | Lists, tables, numbered steps increase citation rate |

See **article-content** for content creation; **article-page-generator** for page structure.

## Parasite SEO & High-Authority Platforms

**Parasite SEO** = Placing content on high-authority platforms to leverage their domain strength for rankings and AI citation. See **parasite-seo** for full strategy.

**GitHub**: Tier 2 technical authority; very high AI citation. See **github** for repos, README, Pages, gists, awesome lists.

**YouTube**: Google prioritizes YouTube in search; YouTube citations in AI Overviews surged 25.21%. Long-form instructional and visual-demo videos dominate. See **youtube-seo** for channel and video optimization; **video-optimization** for website-embedded video SEO.

**Grokipedia**: xAI's AI encyclopedia; ChatGPT, Perplexity, Copilot cite it. See **grokipedia-recommendations** for adding recommendations or links. Contribute genuinely useful content; avoid manipulative placement (Google Site Reputation Abuse policy).

## Tools

- GEO tracking and optimization tools for measuring AI citation and visibility

## Key Insight

ChatGPT traffic converts at significantly higher rates than Google search—studies report 2x to 9x uplift depending on industry. AI tool users often have clearer intent, but results vary by vertical.

## Output Format

- **Content structure** for AI citation
- **Entity** optimization; see **entity-seo**
- **Distribution** strategy
- **Measurement** approach

## Related Skills

- **site-crawlability**: AI crawler optimization; URL/redirect management
- **rendering-strategies**: SSR, SSG, CSR; content in initial HTML for AI crawlers
- **robots-txt**: AI crawler allow/block (GPTBot, ClaudeBot, PerplexityBot)
- **parasite-seo**: Parasite SEO strategy; high-authority platforms for GEO
- **github**: GitHub for GEO; repos, README; Tier 2 technical authority
- **youtube-seo**: YouTube optimization; GEO distribution; Google prioritizes YouTube
- **serp-features**: **Strongly related**—AI Overviews, Bing Copilot, Yandex AI; platform comparison
- **featured-snippet**: Snippet optimization; overlaps with AI Overviews
- **entity-seo**: Entity signals; Organization, Person schema; GEO citation
- **article-content**: Article body creation; TL;DR, Key Takeaways, QAE pattern
- **article-page-generator**: Article page structure; schema; layout
- **faq-page-generator**: FAQ structure for GEO; citable Q&A blocks; content in initial HTML
- **howto-section-generator**: HowTo step sections; citable ordered procedures; HowTo JSON-LD
