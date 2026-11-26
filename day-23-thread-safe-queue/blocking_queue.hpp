// Author: Mashhood Ali
//
// BlockingQueue<T> - a thread-safe bounded blocking queue.
//
// The workhorse of producer/consumer pipelines: one or more producer
// threads push work in, one or more consumer threads pop it out, and
// the queue itself handles all synchronization. This is the same
// structure behind thread-pool task queues, log pipelines, and
// message brokers' in-memory buffers.
//
// Design:
//   * A std::deque<T> holds the items, guarded by a single mutex.
//     Two condition variables separate the two wait conditions:
//     not_full_ (producers wait here) and not_empty_ (consumers
//     wait here), so a push only wakes consumers and a pop only
//     wakes producers - no thundering herd.
//   * Bounded capacity gives backpressure: push() blocks instead of
//     letting an unbounded queue grow until the process runs out of
//     memory. Capacity 0 means unbounded (used only when the caller
//     explicitly wants it).
//   * close() is the shutdown signal: it wakes every waiter, makes
//     push() fail, and lets pop() drain the remaining items before
//     returning false. Consumers loop on "pop until false", so no
//     thread is ever left parked on a dead queue.
//   * try_push/try_pop take a timeout so callers can poll, give up,
//     or do other work instead of blocking forever. Both return a
//     bool instead of throwing, matching std::queue-style usage.
//   * Perfect forwarding in emplace/push keeps move-only types
//     (unique_ptr, futures) working; the queue never copies an item.
//
// Complexity: push/pop O(1) amortized (deque), plus one mutex
// acquisition. Throughput is bounded by lock contention, not by the
// data structure: with N producers and M consumers the queue itself
// never does more than constant work per item.

#ifndef BLOCKING_QUEUE_HPP
#define BLOCKING_QUEUE_HPP

#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <mutex>
#include <utility>

template <typename T>
class BlockingQueue {
public:
    // capacity == 0 means unbounded.
    explicit BlockingQueue(std::size_t capacity = 0) : capacity_(capacity) {}

    BlockingQueue(const BlockingQueue&) = delete;
    BlockingQueue& operator=(const BlockingQueue&) = delete;

    // Blocks until there is room, or the queue is closed.
    // Returns false only when the queue was closed before the item
    // could be enqueued; the item is then NOT consumed by the queue.
    bool push(T item) {
        std::unique_lock<std::mutex> lock(mutex_);
        not_full_.wait(lock, [this] {
            return closed_ || capacity_ == 0 || queue_.size() < capacity_;
        });
        if (closed_) {
            return false;
        }
        queue_.push_back(std::move(item));
        lock.unlock();
        not_empty_.notify_one();
        return true;
    }

    // Constructs the item in place. Same blocking/close rules as push().
    template <typename... Args>
    bool emplace(Args&&... args) {
        std::unique_lock<std::mutex> lock(mutex_);
        not_full_.wait(lock, [this] {
            return closed_ || capacity_ == 0 || queue_.size() < capacity_;
        });
        if (closed_) {
            return false;
        }
        queue_.emplace_back(std::forward<Args>(args)...);
        lock.unlock();
        not_empty_.notify_one();
        return true;
    }

    // Blocks until an item is available, or the queue is closed AND
    // drained. Returns false only when there is nothing left to pop.
    bool pop(T& out) {
        std::unique_lock<std::mutex> lock(mutex_);
        not_empty_.wait(lock, [this] { return closed_ || !queue_.empty(); });
        if (queue_.empty()) {
            return false;  // closed and drained
        }
        out = std::move(queue_.front());
        queue_.pop_front();
        lock.unlock();
        not_full_.notify_one();
        return true;
    }

    // Waits at most `timeout` for room, then gives up.
    // Returns false on timeout or when the queue is closed.
    template <typename Rep, typename Period>
    bool try_push(T item, const std::chrono::duration<Rep, Period>& timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        const bool room = not_full_.wait_for(lock, timeout, [this] {
            return closed_ || capacity_ == 0 || queue_.size() < capacity_;
        });
        if (!room || closed_) {
            return false;
        }
        queue_.push_back(std::move(item));
        lock.unlock();
        not_empty_.notify_one();
        return true;
    }

    // Waits at most `timeout` for an item, then gives up.
    // Returns false on timeout or when the queue is closed and drained.
    template <typename Rep, typename Period>
    bool try_pop(T& out, const std::chrono::duration<Rep, Period>& timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        const bool ready = not_empty_.wait_for(lock, timeout, [this] {
            return closed_ || !queue_.empty();
        });
        if (!ready || queue_.empty()) {
            return false;
        }
        out = std::move(queue_.front());
        queue_.pop_front();
        lock.unlock();
        not_full_.notify_one();
        return true;
    }

    // Signals shutdown: no more pushes, and pop() drains then stops.
    // Safe to call more than once; wakes every waiting thread.
    void close() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            closed_ = true;
        }
        not_empty_.notify_all();
        not_full_.notify_all();
    }

    bool is_closed() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return closed_;
    }

    std::size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.size();
    }

    bool empty() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.empty();
    }

    std::size_t capacity() const noexcept { return capacity_; }

private:
    std::size_t capacity_;
    std::deque<T> queue_;
    mutable std::mutex mutex_;
    std::condition_variable not_empty_;
    std::condition_variable not_full_;
    bool closed_ = false;
};

#endif  // BLOCKING_QUEUE_HPP
