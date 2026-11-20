import Foundation

/// Swift capture → daemon mailbox → page (migration plan D4, §4.2).
/// The capture is ALWAYS posted, even when empty: an empty capture still means
/// "hotkey pressed, no selection" and the page falls back to the active paper.
final class HandoffService {

    /// Blocking — call off the main thread. Returns the capture id, or nil when
    /// the daemon is unreachable (the page then shows its daemon-down state).
    func postCapture(_ capture: CaptureResult, baseURL: URL, timeout: TimeInterval = 3) -> String? {
        let url = baseURL.appendingPathComponent("api/capture")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = timeout
        let body = [
            "selected_text": capture.selectedText,
            "source_app": capture.sourceApp,
            "source_title": capture.sourceTitle,
            "source_url": capture.sourceURL,
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        let semaphore = DispatchSemaphore(value: 0)
        var captureID: String?
        URLSession.shared.dataTask(with: request) { data, response, _ in
            if (response as? HTTPURLResponse)?.statusCode == 200,
               let data,
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let id = object["id"] as? String {
                captureID = id
            }
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + timeout + 0.5)
        return captureID
    }
}
