# 博主发现评分

“发现评分”是 0–100 的候选博主预评分，仅用于博主发现阶段的优先级参考，不是 YouTube 客观字段，也不是最终合作价值评分。

公式：

- 订阅规模适配：30 分
- 命中视频播放量 / 订阅数：30 分
- 互动率：20 分
- 评论率：10 分
- 相对播放速度：10 分

## 订阅规模适配

- 3,000–7,999：0.7 × 30 = 21 分
- 8,000–30,000：1.0 × 30 = 30 分
- 30,001–50,000：0.8 × 30 = 24 分
- 50,001–100,000：0.5 × 30 = 15 分
- 其他：0 分

## 播放 / 订阅比

`view_sub_ratio = views / subscribers`，以 0.4 为满分阈值：`min(view_sub_ratio / 0.4, 1) × 30`。

## 互动率

`engagement = (likes + comments × 2) / views`，以 5% 为满分阈值：`min(engagement / 0.05, 1) × 20`。

## 评论率

`comment_rate = comments / views`，以 0.5% 为满分阈值：`min(comment_rate / 0.005, 1) × 10`。

## 相对播放速度

`relative_velocity = views / max(video_age_days,1) / subscribers`，以 0.02 为满分阈值：`min(relative_velocity / 0.02, 1) × 10`。

## 分档

- A：≥ 85
- B：70–84.999
- C：55–69.999
- D：< 55

同一 Creator 被多个搜索视频命中时，发现页使用该 Creator 得分最高的命中视频作为代表结果；若同分，搜索排名更靠前的结果优先。
