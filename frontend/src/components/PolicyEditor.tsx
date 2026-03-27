import Editor from "@monaco-editor/react";

export default function PolicyEditor(props: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="bg-surface border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-border text-xs text-muted">OPA Policy (Rego)</div>
      <div className="h-[520px]">
        <Editor
          height="520px"
          defaultLanguage="rego"
          theme="vs-dark"
          value={props.value}
          onChange={(v) => props.onChange(v || "")}
          options={{
            minimap: { enabled: false },
            fontSize: 12,
            wordWrap: "on",
          }}
        />
      </div>
    </div>
  );
}

