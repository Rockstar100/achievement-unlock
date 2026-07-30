# Compliance Checklist

## Pre-Deployment Checklist
**Project**: Pet Product Trend Intelligence  
**Environment**: [Development/Staging/Production]  
**Date**: [Date]  
**Owner**: [Engineer Name]

## Data Source Compliance

### Amazon.in
- [ ] Using approved method: [ ] Rainforest API [ ] SerpApi [ ] Official Affiliate API [ ] Scraper (requires separate approval)
- [ ] Rate limits configured: [ ] Max 1 request/second [ ] Custom: ____
- [ ] User-Agent string identifies bot: `PetTrendsBot/1.0 (+https://yourcompany.com/bot)`
- [ ] robots.txt compliance verified
- [ ] No PII collected (only product ASIN, title, price, rating, rank)
- [ ] Data retention: ___ days (configured in pipeline)

### Google Trends
- [ ] Using: [ ] pytrends (unofficial) [ ] Official API (if approved)
- [ ] Rate limits: [ ] Max 1 request/2 seconds [ ] Custom: ____
- [ ] Geographic restriction: `geo='IN'` enforced
- [ ] Timeframe: `now 7-d` (or as configured)
- [ ] No personal data collection

### Flipkart
- [ ] Using: [ ] Official Affiliate API [ ] dvishal485 scraper [ ] Custom implementation
- [ ] Rate limits: [ ] Max 1 request/second [ ] Custom: ____
- [ ] User-Agent string identifies bot
- [ ] robots.txt compliance verified
- [ ] No PII collected (only product ID, title, price, rating, rank)

## Technical Controls

### Rate Limiting
- [ ] All scrapers implement exponential backoff
- [ ] HTTP 429 responses trigger automatic backoff
- [ ] Daily request quotas monitored and alerted
- [ ] Request timing randomized (±10% jitter)

### Monitoring & Alerting
- [ ] Scraper success rate > 95% (alert if < 90%)
- [ ] Error rates tracked by error type (HTTP 4xx/5xx, timeout, parse)
- [ ] Data freshness monitored (alert if no new data in 25 hours)
- [ ] Pipeline latency tracked (alert if > 30 minutes)

### Data Governance
- [ ] Raw data encrypted at rest (ClickHouse settings)
- [ ] Access logs maintained for 90 days
- [ ] Regular audit of access logs (monthly)
- [ ] Data minimization principle applied (only collect needed fields)

## Operational Procedures

### Incident Response
- [ ] Playbook for ToS violation notices
- [ ] Process for immediate scraper suspension
- [ ] Notification template for legal/compliance team
- [ ] Rollback procedure to last known good configuration

### Change Management
- [ ] All scraper changes reviewed for compliance impact
- [ ] Quarterly review of target sites' Terms of Service
- [ ] Annual review of this compliance checklist

## Sign-offs

**Engineering Lead**: ________________________  Date: _________

**Compliance Officer**: ______________________  Date: _________

**Legal Counsel**: __________________________   Date: _________

## Revision History
| Version | Date | Changes | Approved By |
|---------|------|---------|-------------|
| 1.0 | [Date] | Initial version | [Name] |