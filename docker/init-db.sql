-- TrendRadar PostgreSQL 初始化脚本
-- 创建中文全文检索所需扩展和 news_articles 表

CREATE EXTENSION IF NOT EXISTS zhparser;

-- 使用 zhparser 作为中文分词器
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING FOR n,v,a,i,e,l WITH simple;

CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMP WITH TIME ZONE,
    category_l1 TEXT NOT NULL DEFAULT '',
    category_l2 TEXT NOT NULL DEFAULT '',
    keywords TEXT[] NOT NULL DEFAULT '{}',
    crawl_count INTEGER NOT NULL DEFAULT 1,
    crawl_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 标题唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_articles_title ON news_articles (title);

-- 中文全文检索索引（zhparser 分词）
CREATE INDEX IF NOT EXISTS idx_news_articles_title_fts ON news_articles
    USING GIN (to_tsvector('chinese', title));

-- 关键词数组索引（用于关键词筛选）
CREATE INDEX IF NOT EXISTS idx_news_articles_keywords ON news_articles USING GIN (keywords);

-- 发布时间索引（用于日期筛选和排序）
CREATE INDEX IF NOT EXISTS idx_news_articles_published_at ON news_articles (published_at DESC);

-- 抓取时间索引
CREATE INDEX IF NOT EXISTS idx_news_articles_crawl_time ON news_articles (crawl_time DESC);

-- 一级分类索引
CREATE INDEX IF NOT EXISTS idx_news_articles_category_l1 ON news_articles (category_l1);

-- 复合索引：关键词 + 发布日期
CREATE INDEX IF NOT EXISTS idx_news_articles_keywords_date ON news_articles
    USING GIN (keywords) WHERE published_at IS NOT NULL;

-- 迁移：为已有表添加 crawl_count 列
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'news_articles'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'news_articles' AND column_name = 'crawl_count'
    ) THEN
        ALTER TABLE news_articles ADD COLUMN crawl_count INTEGER NOT NULL DEFAULT 1;
    END IF;
END $$;
