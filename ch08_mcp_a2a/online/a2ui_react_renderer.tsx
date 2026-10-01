// React component rendering Agent-to-UI native widgets.
// Instead of the LLM generating raw HTML (insecure), the LLM emits a JSON payload:
// { "type": "chart", "data": [1,2,3] }
// The dashboard maps that payload strictly to verified React components.

const AgentWidgetRenderer = ({ payload }) => {
    switch(payload.type) {
        case 'chart':
            return <BarChart data={payload.data} />;
        case 'alert':
            return <AlertBox message={payload.text} severity={payload.level} />;
        default:
            return <p>{payload.text}</p>;
    }
}
