import Foundation

/// Polls GET /api/health every 15 s (migration plan §6.2), driving the menu-bar
/// icon and offering a quick blocking check for the hotkey path.
final class HealthCheck: ObservableObject {

    @Published private(set) var daemonUp = false
    /// Version reported by /api/health (e.g. "0.1.0+a1b2c3") — makes a stale
    /// daemon identifiable at a glance (the stale-daemon gotcha, §7.3).
    @Published private(set) var daemonVersion = ""
    /// False = daemon reachable but OPENROUTER_API_KEY unset (asks will 503).
    @Published private(set) var apiKeyPresent = true

    private let healthURL: URL
    private var timer: Timer?

    init(baseURL: URL) {
        healthURL = baseURL.appendingPathComponent("api/health")
    }

    func start() {
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            self?.poll()
        }
    }

    private func poll() {
        var request = URLRequest(url: healthURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            let up = (response as? HTTPURLResponse)?.statusCode == 200
            var version = ""
            var apiKeyPresent = true
            if up, let data,
               let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
                version = object["version"] as? String ?? ""
                if let present = object["api_key_present"] as? Bool { apiKeyPresent = present }
            }
            DispatchQueue.main.async {
                self?.daemonUp = up
                self?.daemonVersion = version
                self?.apiKeyPresent = apiKeyPresent
            }
        }.resume()
    }

    /// Blocking on/off check — call off the main thread only.
    func isUp(timeout: TimeInterval) -> Bool {
        var request = URLRequest(url: healthURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = timeout
        let semaphore = DispatchSemaphore(value: 0)
        var up = false
        URLSession.shared.dataTask(with: request) { _, response, _ in
            up = (response as? HTTPURLResponse)?.statusCode == 200
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + timeout + 0.5)
        return up
    }
}
