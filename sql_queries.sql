-- Dataset: synthetic media_ratings_synthetic.csv
-- Run these in the app's SQL Practice tab (one SELECT statement at a time).

-- 1. Audience exposure by platform
SELECT platform, ROUND(SUM(viewers) / 1000000.0, 2) AS exposures_millions
FROM ratings
GROUP BY platform
ORDER BY exposures_millions DESC;

-- 2. Highest-rated sports programs
SELECT program, network, ROUND(AVG(rating_pct), 3) AS avg_regional_rating
FROM ratings
WHERE genre = 'Sports'
GROUP BY program, network
ORDER BY avg_regional_rating DESC;

-- 3. Monthly streaming trends
SELECT SUBSTR(date, 1, 7) AS year_month,
       ROUND(SUM(viewers) / 1000000.0, 2) AS exposure_millions
FROM ratings
WHERE platform = 'Streaming'
GROUP BY SUBSTR(date, 1, 7)
ORDER BY year_month;

-- 4. Advertising spend by network
SELECT network,
       ROUND(SUM(ad_spend_usd) / 1000000.0, 2) AS ad_spend_millions
FROM ratings
GROUP BY network
ORDER BY ad_spend_millions DESC;
