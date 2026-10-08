// ai-log.js
// 以脚本自身位置为基准定位站点接口
const aiLogSiteRoot = new URL('../../', document.currentScript.src);

function saveAIQuestion(question, userName) {
    const now = new Date();
    const time = now.toISOString().replace('T', ' ').substring(0, 19);
    const data = {
        time: time,
        question: question,
        user: userName || '游客'
    };
    fetch(new URL('api/ollama/save-ai-question', aiLogSiteRoot), {
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
