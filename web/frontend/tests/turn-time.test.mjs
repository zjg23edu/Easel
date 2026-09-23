import assert from 'node:assert/strict';
import test from 'node:test';
import { formatTurnDuration } from '../src/lib/turnTime.ts';

test('不足一分钟只显示秒', () => {
  assert.equal(formatTurnDuration(0), '0秒');
  assert.equal(formatTurnDuration(12_400), '12秒');
});

test('超过一分钟显示分和秒', () => {
  assert.equal(formatTurnDuration(65_000), '1分05秒');
});
