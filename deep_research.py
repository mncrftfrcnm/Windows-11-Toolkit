import requests
import requests_cache
from duckduckgo_search import ddg
from newspaper import Article
from transformers import pipeline
from multiprocessing import Pool, cpu_count
import functools

# Initialize a requests cache (stores GET responses)
requests_cache.install_cache('deep_research_cache', expire_after=3600)  # cache expires in 1 hour

class DeepResearchClone:
    def __init__(self,
                 search_engine='duckduckgo',
                 summarizer_model='facebook/bart-large-cnn',
                 qa_model='distilbert-base-uncased-distilled-squad',
                 use_multiprocessing=True):
        # Initialize search settings
        self.search_engine = search_engine
        # Summarization pipeline
        self.summarizer = pipeline('summarization', model=summarizer_model)
        # QA pipeline
        self.qa_pipeline = pipeline('question-answering', model=qa_model)
        # Option to parallelize fetch+summarize
        self.use_multiprocessing = use_multiprocessing

    def search(self, query, max_results=5):
        """
        Perform web search using DuckDuckGo and return list of URLs
        """
        results = ddg(query, max_results=max_results)
        return [r['href'] for r in results]

    def fetch_and_summarize(self, url, max_length=150, min_length=40):
        """
        Fetch page, parse text, and summarize.
        Returns a tuple (url, summary_text).
        """
        try:
            # Download and parse via newspaper3k
            article = Article(url)
            article.download()
            article.parse()
            text = article.text
            if not text:
                return (url, '')
            # Summarize using transformer pipeline
            summary = self.summarizer(
                text, max_length=max_length, min_length=min_length, do_sample=False
            )[0]['summary_text']
            return (url, summary)
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return (url, '')

    def research(self, query, question=None, max_results=5):
        # Search web
        urls = self.search(query, max_results)
        print(f"Found {len(urls)} URLs: {urls}")

        # Fetch & summarize (optionally in parallel)
        summaries = {}
        if self.use_multiprocessing:
            workers = max(1, cpu_count() - 1)
            with Pool(workers) as pool:
                func = functools.partial(self.fetch_and_summarize)
                for url, summary in pool.map(func, urls):
                    if summary:
                        summaries[url] = summary
                        print(f"-- Summary for {url}:\n{summary}\n")
        else:
            for url in urls:
                url, summary = self.fetch_and_summarize(url)
                if summary:
                    summaries[url] = summary
                    print(f"-- Summary for {url}:\n{summary}\n")

        # Answer a question if provided
        if question and summaries:
            combined_context = ' '.join(summaries.values())
            answer = self.qa_pipeline(question=question, context=combined_context)['answer']
            print(f"Answer: {answer}")
            return summaries, answer
        return summaries


def main():
    print("=== Deep Research Clone ===")
    query = input("Enter your search query: ")
    if not query.strip():
        print("Query cannot be empty.")
        return
    q = input("Enter a specific question to answer (optional): ") or None
    try:
        max_r = int(input("Max search results [5]: ") or 5)
    except ValueError:
        max_r = 5
    mp_input = input("Use multiprocessing? (y/n) [y]: ")
    use_mp = not (mp_input.strip().lower() in ['n', 'no'])

    dr = DeepResearchClone(use_multiprocessing=use_mp)
    result = dr.research(query, question=q, max_results=max_r)

    # Optionally, process result further or save to file

if __name__ == '__main__':
    main()
