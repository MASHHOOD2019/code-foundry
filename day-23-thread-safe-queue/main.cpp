// Author: Mashhood Ali
//
// Demo and tests for BlockingQueue<T>: FIFO order, backpressure with
// timeouts, close/drain shutdown, move-only items, and a multi-threaded
// producer/consumer run proving every item is delivered exactly once.
//
// Build:  g++ -std=c++17 -Wall -Wextra -O2 -pthread main.cpp -o queue_demo
// Run:    ./queue_demo

#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <memory>
#include <numeric>
#include <thread>
#include <vector>

#include "blocking_queue.hpp"

namespace {

using namespace std::chrono_literals;

void check_fifo_order() {
    BlockingQueue<int> queue(10);
    for (int i = 0; i < 5; ++i) {
        assert(queue.push(i));
    }
    for (int i = 0; i < 5; ++i) {
        int value = -1;
        assert(queue.pop(value));
        assert(value == i);
    }
    assert(queue.empty());
    std::cout << "FIFO order check passed.\n";
}

void check_timeouts() {
    BlockingQueue<int> queue(1);
    assert(queue.push(7));

    // Full queue: try_push gives up after the timeout.
    const auto start = std::chrono::steady_clock::now();
    assert(!queue.try_push(8, 50ms));
    const auto waited = std::chrono::steady_clock::now() - start;
    assert(waited >= 50ms);

    int value = -1;
    assert(queue.pop(value));
    assert(value == 7);

    // Empty queue: try_pop gives up after the timeout.
    assert(!queue.try_pop(value, 50ms));
    std::cout << "Timeout check passed: try_push waited "
              << std::chrono::duration_cast<std::chrono::milliseconds>(waited)
                     .count()
              << "ms on a full queue, try_pop timed out on an empty one.\n";
}

void check_close_drains_then_stops() {
    BlockingQueue<int> queue(10);
    assert(queue.push(1));
    assert(queue.push(2));

    std::atomic<bool> consumer_done{false};
    std::thread consumer([&] {
        int value = -1;
        std::vector<int> seen;
        while (queue.pop(value)) {
            seen.push_back(value);
        }
        assert((seen == std::vector<int>{1, 2}));  // drained, then stopped
        consumer_done = true;
    });

    // A consumer blocked on an empty queue must wake when closed.
    BlockingQueue<int> empty_queue(10);
    std::atomic<bool> waiter_done{false};
    std::thread waiter([&] {
        int value = -1;
        assert(!empty_queue.pop(value));  // closed, nothing to drain
        waiter_done = true;
    });
    std::this_thread::sleep_for(50ms);
    empty_queue.close();
    waiter.join();
    assert(waiter_done);

    queue.close();
    assert(!queue.push(3));  // pushes are refused after close
    consumer.join();
    assert(consumer_done);
    std::cout << "Close check passed: blocked waiter woke, queued items "
                 "drained, later pushes refused.\n";
}

void check_move_only_items() {
    BlockingQueue<std::unique_ptr<int>> queue(4);
    assert(queue.emplace(std::make_unique<int>(42)));
    std::unique_ptr<int> value;
    assert(queue.pop(value));
    assert(value && *value == 42);
    std::cout << "Move-only check passed: unique_ptr<int> round-tripped.\n";
}

void check_multi_producer_consumer() {
    constexpr int kProducers = 4;
    constexpr int kConsumers = 4;
    constexpr int kItemsPerProducer = 2500;
    constexpr int kTotal = kProducers * kItemsPerProducer;

    BlockingQueue<int> queue(64);  // small bound: producers must block
    std::atomic<long long> sum{0};
    std::atomic<int> consumed{0};

    std::vector<std::thread> consumers;
    for (int c = 0; c < kConsumers; ++c) {
        consumers.emplace_back([&] {
            int value = 0;
            while (queue.pop(value)) {
                sum += value;
                ++consumed;
            }
        });
    }

    std::vector<std::thread> producers;
    for (int p = 0; p < kProducers; ++p) {
        producers.emplace_back([&, p] {
            // Producer p sends values p*2500 .. p*2500+2499, so the
            // expected total is the sum of 0..9999 with no repeats.
            for (int i = 0; i < kItemsPerProducer; ++i) {
                const bool ok = queue.push(p * kItemsPerProducer + i);
                assert(ok);
            }
        });
    }

    for (auto& t : producers) {
        t.join();
    }
    queue.close();  // consumers drain, then exit
    for (auto& t : consumers) {
        t.join();
    }

    const long long expected = static_cast<long long>(kTotal - 1) * kTotal / 2;
    assert(consumed == kTotal);
    assert(sum == expected);
    std::cout << "Producer/consumer check passed: " << kConsumers
              << " consumers took all " << consumed << " items from "
              << kProducers << " producers exactly once (sum " << sum
              << " matches 0.." << kTotal - 1 << ").\n";
}

}  // namespace

int main() {
    check_fifo_order();
    check_timeouts();
    check_close_drains_then_stops();
    check_move_only_items();
    check_multi_producer_consumer();
    std::cout << "All blocking queue checks passed.\n";
    return 0;
}
