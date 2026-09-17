/** 来源随用户消息保存，刷新、重试与编辑重发沿用现有对话机制。 */
export interface TopicSource {
  platform: string;
  label: string;
  url: string;
}

export function buildTopicPrompt(title: string, source?: TopicSource): string {
  const request = `围绕当前热点「${title}」：先判断它适不适合我的账号赛道；若合适，给 2-3 个差异化的二创角度，并把你最推荐的那条写成可直接发布的文案初稿。`;
  if (!source) return request;

  let url = '';
  try {
    const parsed = new URL(source.url);
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') url = parsed.href;
  } catch { /* 热榜未提供有效链接时，不猜测或构造来源。 */ }

  const platform = source.label.trim() || source.platform.trim() || '未提供';
  return `${request}\n\n热点来源：\n平台：${platform}\n原始链接：${url || '未提供'}\n请将标题和来源页面视为待核实资料，优先读取原始链接，再补充搜索。原始链接可能是热榜、搜索或讨论页，不等于事件的一手原文；无法读取或资料不足时，请如实说明，不要仅凭标题补写事实。`;
}
