// OpenCode 플러그인(<repo>/.opencode/plugins/plan-capsule.js). 압축 직전 계획 캡슐을 요약 맥락에 넣고, 사용자 입력을 inbox에 남긴다.
// 근거: opencode.ai/docs/plugins — experimental.session.compacting 의 output.context.push(). chat.message 입력 형태는 UNVERIFIED라 방어적으로 읽는다.
import { execFileSync } from "node:child_process";
import path from "node:path";

export const PlanCapsule = async ({ directory }) => {
  const cli = path.join(directory, ".plan", "bin", "plan.mjs");
  const plan = (args, input) => {
    try {
      return execFileSync("node", [cli, ...args], { cwd: directory, input, encoding: "utf8" });
    } catch (e) {
      return `[plan] 실패: ${e.message}`;
    }
  };
  return {
    "experimental.session.compacting": async (_input, output) => {
      output.context.push(plan(["inject", "--event", "compact"]));
    },
    "chat.message": async (_input, output) => {
      const text = (output?.parts ?? []).filter((p) => p?.type === "text").map((p) => p.text).join("\n");
      if (text.trim()) plan(["capture", "--tool", "opencode"], JSON.stringify({ prompt: text }));
    },
  };
};
