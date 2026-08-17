"""The request/offer direction axis — a single vector that separates "I need" from "I offer".

Embeddings encode *topic*, not the direction of a transaction: "someone looking to hire a
developer" and "[FOR HIRE] Full Stack Developer" share almost all their topical content, so
cosine similarity ranks the wrong side of the market first. Measured on real r/forhire data, raw
similarity put six offer posts above every request (docs/PROGRESS.md, 2026-07-30).

The fix is to estimate that one axis separately and score against it. Because the phrasings below
mention no job, skill, or industry, the axis they define encodes direction and nothing else — which
is what stops it from suppressing a genuine match whose wording happens to resemble an example.
A per-watcher contrastive vector separated better on average and did exactly that, so it was
rejected; see the same PROGRESS entry.
"""

from __future__ import annotations

import logging
import math

from app.workers.embedding_source import EmbeddingProvider

logger = logging.getLogger(__name__)

# Deliberately topic-free: no job title, skill, industry, or price. Anything specific here would
# leak topic into the axis and let it penalise real matches on that topic.
REQUEST_PHRASINGS = [
    "[Hiring] Looking to hire someone for this project, paid work.",
    "We need help with a task and are willing to pay someone to do it.",
    "Looking for someone to do this work for us, will pay.",
    "Need to find a person to take on this job.",
    "Seeking someone who can handle this for us.",
]

OFFER_PHRASINGS = [
    "[FOR HIRE] I am available for freelance work, portfolio attached.",
    "Experienced professional available for hire, competitive hourly rate.",
    "I offer my services, contact me if you are interested.",
    "Available for new projects, here is what I can do for you.",
    "Taking on new clients, message me to discuss.",
]


# Scale a vector to unit length so dot products are cosines. Guards the zero vector.
def normalise(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return list(vector)
    return [value / length for value in vector]


# Average a set of vectors component-wise. Used to find the centre of each phrasing group.
def mean_vector(vectors: list[list[float]]) -> list[float]:
    count = len(vectors)
    width = len(vectors[0])
    return [sum(vector[index] for vector in vectors) / count for index in range(width)]


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


# Embed both phrasing groups and return the unit vector pointing from "request" toward "offer".
# Called once per worker process at startup; the same inputs always yield the same axis.
async def compute_direction_axis(provider: EmbeddingProvider) -> list[float]:
    vectors = await provider.embed(REQUEST_PHRASINGS + OFFER_PHRASINGS)
    request_mean = mean_vector(vectors[: len(REQUEST_PHRASINGS)])
    offer_mean = mean_vector(vectors[len(REQUEST_PHRASINGS) :])
    axis = normalise([o - r for o, r in zip(offer_mean, request_mean, strict=True)])
    logger.info(
        "direction axis computed from %d request / %d offer phrasings",
        len(REQUEST_PHRASINGS),
        len(OFFER_PHRASINGS),
    )
    return axis


# Where a post sits on the axis: positive reads like an offer, negative like a request.
# Roughly ±0.1 in practice, so it is a nudge to similarity rather than a replacement for it.
def direction_score(post_embedding: list[float], axis: list[float]) -> float:
    return dot(normalise(post_embedding), axis)


# How much to subtract from a candidate's similarity, given what the watcher is looking for.
#
# The penalty is one-sided on purpose: a post pointing the *wrong* way for this watcher is pushed
# down, but a post pointing the right way gets no bonus. Rewarding the right direction would let a
# strongly-worded but topically irrelevant post outrank a well-matched one, which is the mirror of
# the bug being fixed here.
def direction_penalty(score: float, watcher_direction: str) -> float:
    if watcher_direction == "offering":
        # This watcher wants offers, so a request-leaning post (negative score) is the mismatch.
        return max(0.0, -score)
    return max(0.0, score)
