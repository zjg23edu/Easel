import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTopicPrompt } from '../src/lib/topicPrompt.ts';

test('热点的标题、平台和完整来源链接进入实际发送的消息', () => {
  const url = 'https://www.zhihu.com/question/123?utm_source=radar&x=1#answer';
  const message = buildTopicPrompt('小米 MiMo 训练', { platform: 'zhihu', label: '知乎', url });
  assert.ok(message.includes('「小米 MiMo 训练」'));
  assert.ok(message.includes('平台：知乎'));
  assert.ok(message.includes(`原始链接：${url}`));
  assert.ok(message.includes('不等于事件的一手原文'));
});

test('标题型选题入口保持原有请求，不伪造来源', () => {
  const message = buildTopicPrompt('选题库中的想法');
  assert.ok(message.includes('「选题库中的想法」'));
  assert.ok(!message.includes('热点来源'));
});

test('缺失或非网页链接明确标记未提供', () => {
  for (const url of ['', 'not-a-url', 'javascript:alert(1)', 'file:///etc/passwd']) {
    const message = buildTopicPrompt('热点', { platform: 'zhihu', label: '', url });
    assert.ok(message.includes('平台：zhihu'));
    assert.ok(message.includes('原始链接：未提供'));
  }
});


test('历史或手动选题可发送，来源缺失显式展示', () => {
  const message = buildTopicPrompt('手动灵感', { platform: '', label: '', url: '' });
  assert.ok(message.includes('「手动灵感」'));
  assert.ok(message.includes('平台：未提供'));
  assert.ok(message.includes('原始链接：未提供'));
});
