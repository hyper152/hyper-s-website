// ai-log.js
// 记录AI提问到 /data/ai.json

function saveAIQuestion(question, userName) {
    const now = new Date();
    const time = now.toISOString().replace('T', ' ').substring(0, 19);
    const data = {
        time: time,
        question: question,
        user: userName || '游客'
    };
    fetch('/api/ollama/save-ai-question', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }).then(r => r.json()).then(res => {
        // 可选：处理返回
        if (res && res.status === 'ok') {
            console.log('AI问题已保存');
        }
    }).catch(e => {
        console.warn('AI问题保存失败', e);
    });
}
