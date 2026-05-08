from .base import NoSQLDatabase
import logging 

logger = logging.getLogger(__name__)

class FirestoreDatabase(NoSQLDatabase):
    def __init__(self, credentials=None):
        from google.cloud import firestore
        self.db = firestore.Client(credentials=credentials)

    def save_response(self, responses, batch_size=200):
        batches = []
        batch = self.db.batch()
        for i, (id_, data) in enumerate(responses):
            ref = self.db.collection("statens_vegvesen").document(id_)
            batch.set(ref, data)
            if (i + 1) % batch_size == 0:
                batches.append(batch)
                batch = self.db.batch()
        if batch:
            batches.append(batch)

        self.db.commit_batches(batches)
        logger.info(f"Saved {len(responses)} responses to Firestore in {len(batches)} batches.")