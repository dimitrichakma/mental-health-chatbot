-- Ad-hoc review of tester conversations + feedback.
-- Usage:  railway connect Postgres    then  \i review_logs.sql   (or paste)

-- summary
SELECT count(*)                                  AS conversations,
       count(*) FILTER (WHERE feedback = 1)      AS thumbs_up,
       count(*) FILTER (WHERE feedback = -1)     AS thumbs_down,
       count(*) FILTER (WHERE feedback_note <> '') AS with_notes,
       count(*) FILTER (WHERE is_crisis)         AS crisis,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)) AS median_ms
FROM conversation_log;

-- everything a tester flagged (thumbs-down or left a note), newest first
SELECT id, ts, feedback, feedback_note, paths_used, is_crisis,
       left(question, 120)  AS question,
       left(answer, 300)    AS answer
FROM conversation_log
WHERE feedback = -1 OR feedback_note IS NOT NULL
ORDER BY ts DESC;

-- full recent transcript
SELECT id, ts, thread_id, feedback, paths_used, is_crisis, latency_ms,
       question, answer
FROM conversation_log
ORDER BY ts DESC
LIMIT 100;
