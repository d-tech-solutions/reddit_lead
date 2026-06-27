# LeadRadar AI - Product Requirements Document (PRD)

## Product Overview

LeadRadar AI is an AI-powered lead discovery platform that continuously monitors Reddit and identifies high-intent opportunities for freelancers and small agencies.

Unlike traditional keyword alert tools, LeadRadar understands intent, business problems, urgency, and buying signals to surface qualified leads and generate suggested responses.

Initial target users:

* Freelance developers
* Small software agencies
* Flutter developers
* Laravel developers
* AI consultants
* Automation consultants

Version 1 focuses exclusively on Reddit.

---

# Problem Statement

Current tools such as F5Bot rely on exact keyword matching.

Problems:

* Too much noise
* Low lead quality
* No lead prioritization
* No business context
* No CRM workflow
* No AI-generated responses

Users spend hours manually searching Reddit and still miss opportunities.

LeadRadar solves this by converting Reddit conversations into actionable sales opportunities.

---

# Product Vision

Transform Reddit conversations into qualified leads.

Instead of:

Keyword → Email

LeadRadar provides:

Conversation → AI Understanding → Lead Qualification → Notification → CRM → Response

---

# Target Users

## Freelancer

Needs:

* Find projects quickly
* Reply before competitors
* Avoid wasting time on low-quality posts

Success Metric:

* More client conversations

---

## Small Agency

Needs:

* Consistent lead flow
* Team visibility
* Lead tracking

Success Metric:

* More qualified opportunities

---

# MVP Scope

Data Sources:

* Reddit only

Notifications:

* Telegram
* Email

Authentication:

* Email/password
* Google OAuth

AI Features:

* Lead scoring
* Lead summaries
* Suggested replies

CRM:

* New
* Replied
* Interested
* Won
* Lost

---

# Core Features

## Reddit Monitoring

System continuously monitors selected subreddits.

Examples:

* r/startups
* r/smallbusiness
* r/entrepreneur
* r/SaaS
* r/forhire

System collects:

* Title
* Content
* Author
* Subreddit
* URL
* Timestamp

---

## AI Lead Qualification

For every post:

AI determines:

* Intent score
* Industry
* Business type
* Estimated urgency
* Estimated budget
* Recommended service

Output:

{
score: 95,
industry: "Restaurant",
urgency: "High",
intent: "Website Development"
}

---

## Lead Scoring

Scoring range:

0-100

Categories:

0-40 = Low

41-70 = Medium

71-100 = High

Factors:

* Buying intent
* Business owner signals
* Budget mentions
* Urgency
* Need for software

---

## AI Summary

Example:

Restaurant owner seeking website rebuild with online ordering functionality. Budget approximately $5000. High buying intent.

---

## AI Reply Generator

Example:

Hi! I noticed you're looking to rebuild your restaurant website. I specialize in custom web applications and would be happy to discuss your requirements.

---

## Notifications

Trigger:

Score >= User Threshold

Channels:

* Telegram
* Email

Notification includes:

* Title
* Score
* Summary
* Open Reddit button
* Copy Reply button

---

## Lead Dashboard

Views:

* New Leads
* High Intent Leads
* Saved Leads
* Won Leads
* Lost Leads

Filters:

* Score
* Industry
* Service Type
* Date

---

## CRM

Lead Status:

New
↓
Replied
↓
Interested
↓
Won

or

Lost

Store:

* Notes
* Follow-up date
* Custom tags

---

# System Architecture

Reddit API
↓
Collector Service
↓
PostgreSQL
↓
Redis Queue
↓
AI Worker
↓
Lead Intelligence
↓
Notification Service
↓
Dashboard

---

# Tech Stack

## Frontend

Next.js 15

React

TypeScript

Tailwind CSS

shadcn/ui

TanStack Query

Zustand

---

## Backend

FastAPI

Python 3.13

Pydantic

SQLAlchemy

Alembic

---

## Database

PostgreSQL

---

## Queue

Redis

Celery

---

## AI

OpenRouter

Provider abstraction layer

Supported later:

* OpenAI
* Claude
* Gemini
* Local Models

---

## Authentication

JWT

Google OAuth

Refresh Tokens

---

## Notifications

Telegram Bot API

Resend Email

---

## Search

PostgreSQL Full Text Search

Upgrade later:

Meilisearch

---

## Monitoring

Sentry

Structured Logging

Health Checks

---

## Deployment

Docker

Docker Compose

Nginx

Hetzner VPS

---

# Database Tables

users

user_preferences

reddit_posts

lead_analysis

lead_status

notifications

reply_templates

saved_leads

subscriptions

---

# User Preferences

Monitor Outcomes:

* Website Projects
* Mobile Apps
* SaaS MVPs
* Automation Projects
* AI Projects

Threshold:

Minimum Lead Score

Notification Channels

Preferred Industries

---

# API Endpoints

POST /auth/login

POST /auth/register

GET /leads

GET /leads/{id}

PATCH /leads/{id}/status

GET /notifications

GET /analytics

POST /settings

POST /generate-reply

---

# Analytics

Metrics:

* Leads Found
* Leads Replied
* Leads Won
* Conversion Rate
* Average Lead Score
* Top Industries

---

# Pricing

## Free

20 leads/month

Email notifications

---

## Pro

Unlimited leads

Telegram

CRM

AI replies

---

## Agency

Multiple users

Shared pipeline

Advanced analytics

---

# Development Phases

Phase 1

Personal Tool

* Reddit collector
* AI scoring
* Telegram notifications

Phase 2

Private Beta

* Dashboard
* CRM
* Email notifications

Phase 3

Public SaaS

* Billing
* Teams
* Analytics

Phase 4

Expansion

* Hacker News
* Indie Hackers
* GitHub Discussions
* X

---

# Success Metrics

Personal Validation:

* Generate first lead

MVP Validation:

* 10 active users

Product Validation:

* First paying customer

Growth Validation:

* 100 paying users

---

# Long-Term Vision

Become the AI-powered lead intelligence platform for freelancers and agencies.

Users define desired outcomes instead of keywords.

The platform discovers opportunities, prioritizes them, generates responses, and tracks conversion automatically.
