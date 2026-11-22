// Author: Mashhood Ali
//
// A fixed-size thread pool: submit work with enqueue() and get a
// std::future for the result. One mutex + condition variable guard
// the task queue; workers sleep while it is empty and wake on
// notify. Shutdown is graceful: the destructor stops accepting new
// work, lets already-queued tasks finish, then joins every worker,
// so no submitted task is ever dropped.
//
// Complexity: enqueue is O(1) amortised; a worker picks up a task in
// O(1). Idle workers cost nothing but a blocked condition-variable
// wait. Ideal when the same pool serves many short jobs instead of
// paying a thread-spawn cost per job.
//
// Usage:
//   ThreadPool pool(4);
//   auto f = pool.enqueue([] { return 40 + 2; });
//   std::cout << f.get() << '\n';  // 42

#pragma once

#include <algorithm>
#include <condition_variable>
#include <cstddef>
#include <functional>
#include <future>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

class ThreadPool {
public:
    // Spawns `thread_count` workers. Defaults to the hardware thread
    // count (at least 1). An explicit 0 is treated as "use the
    // hardware count", never as a zero-worker pool.
    explicit ThreadPool(std::size_t thread_count = std::thread::hardware_concurrency())
        : thread_count_(thread_count == 0
                            ? std::max<std::size_t>(std::thread::hardware_concurrency(), 1)
                            : thread_count) {
        workers_.reserve(thread_count_);
        for (std::size_t i = 0; i < thread_count_; ++i) {
            workers_.emplace_back([this] { worker_loop(); });
        }
    }

    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;

    // Stops accepting work, drains the queue, then joins the workers.
    ~ThreadPool() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stop_ = true;
        }
        condition_.notify_all();
        for (std::thread& worker : workers_) {
            if (worker.joinable()) {
                worker.join();
            }
        }
    }

    // Runs `task` on a worker thread and returns a future for its
    // result. Exceptions thrown by the task are captured by the
    // future and rethrown by get(). Throws std::runtime_error if
    // called after shutdown began. O(1) amortised.
    template <typename F, typename... Args>
    auto enqueue(F&& task, Args&&... args)
        -> std::future<std::invoke_result_t<F, Args...>> {
        using ReturnType = std::invoke_result_t<F, Args...>;

        auto bound = std::bind(std::forward<F>(task), std::forward<Args>(args)...);
        auto packaged = std::make_shared<std::packaged_task<ReturnType()>>(std::move(bound));
        std::future<ReturnType> result = packaged->get_future();

        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stop_) {
                throw std::runtime_error("enqueue on stopped ThreadPool");
            }
            tasks_.emplace([packaged] { (*packaged)(); });
        }
        condition_.notify_one();
        return result;
    }

    std::size_t thread_count() const { return thread_count_; }

    // Number of tasks waiting in the queue (0 once workers pick them up).
    std::size_t pending() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return tasks_.size();
    }

private:
    void worker_loop() {
        for (;;) {
            std::function<void()> task;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                condition_.wait(lock, [this] { return stop_ || !tasks_.empty(); });
                if (tasks_.empty()) {
                    return;  // stop_ is set and the queue is drained
                }
                task = std::move(tasks_.front());
                tasks_.pop();
            }
            task();
        }
    }

    std::size_t thread_count_;
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;

    mutable std::mutex mutex_;
    std::condition_variable condition_;
    bool stop_ = false;
};
