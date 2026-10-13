// 网络块可能在 JSON 或 UTF-8 字符中间断开；按完整 NDJSON 行读取。
async function readChatStream(stream, onPacket) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let newline;
            while ((newline = buffer.indexOf("\n")) !== -1) {
                const line = buffer.slice(0, newline).trim();
                buffer = buffer.slice(newline + 1);
                if (line) onPacket(JSON.parse(line));
            }
        }
        buffer += decoder.decode();
        if (buffer.trim()) onPacket(JSON.parse(buffer));
    } catch (error) {
        await reader.cancel().catch(() => {});
        throw error;
    } finally {
        reader.releaseLock();
    }
}
