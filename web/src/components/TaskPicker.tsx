import type { TaskChoice } from "@/lib/task-workflow";

export function TaskPicker({ tasks, value, onChange, english, disabled = false }: {
  tasks: TaskChoice[]; value: string; onChange: (id: string) => void; english: boolean; disabled?: boolean;
}) {
  return <div className="form-grid real-campaign-form"><label>{english ? "Choose this account's task" : "选择当前账户的任务"}
    <select value={value} onChange={event => onChange(event.target.value)} disabled={disabled}>
      <option value="">{english ? "Select a task before continuing" : "请先选择任务再继续"}</option>
      {tasks.map(task => <option key={task.task_id} value={task.task_id}>{task.title || (english ? "Untitled task" : "未命名任务")} — {task.task_id}</option>)}
    </select>
  </label></div>;
}
