class InvertedIndex:
    def __init__(self):
        self.index = {}
    def tokenize(self, text: str):
        return text.lower().split()
    def add_document(self, doc_id: int, text: str):
        words = self.tokenize(text)
        for word in words:
            if word not in self.index:
                self.index[word] = set()
            self.index[word].add(doc_id)
    def search(self, query: str):
        words = self.tokenize(query)
        doc_scores = {}
        for word in words:
            if word in self.index:
                for doc_id in self.index[word]:
                    doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1
        return doc_scores
