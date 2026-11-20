// Author: Mashhood Ali
//
// Demo and checks for the token bucket rate limiter.
//
// Verifies burst limits, refill over time, rejection of oversized
// requests, and that concurrent callers can never overspend the
// bucket (with a zero refill rate, exactly `capacity` requests are
// granted across all threads, no matter how many compete).

#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>
#include <vector>

#include "rate_limiter.hpp"

int main() {
    using namespace std::chrono_literals;

    // 1. Burst: a fresh bucket allows exactly `capacity` requests.
    {
        TokenBucketRateLimiter limiter(10.0, 5.0);
        for (int i = 0; i < 5; ++i) {
            assert(limiter.try_acquire());
        }
        assert(!limiter.try_acquire());
        std::cout << "Burst check passed: 5 allowed, 6th rejected.\n";
    }

    // 2. Refill: at 10 tokens/sec, ~200 ms earns back ~2 tokens.
    {
        TokenBucketRateLimiter limiter(10.0, 5.0);
        for (int i = 0; i < 5; ++i) {
            assert(limiter.try_acquire());
        }
        std::this_thread::sleep_for(210ms);
        assert(limiter.try_acquire());
        assert(limiter.try_acquire());
        assert(!limiter.try_acquire());
        std::cout << "Refill check passed: 2 tokens back after ~200 ms.\n";
    }

    // 3. Oversized and invalid requests never spend tokens.
    {
        TokenBucketRateLimiter limiter(10.0, 5.0);
        assert(!limiter.try_acquire(6.0));   // larger than the bucket
        assert(!limiter.try_acquire(0.0));   // nothing to spend
        assert(!limiter.try_acquire(-1.0));  // negative
        assert(limiter.available() == 5.0);  // bucket untouched
        std::cout << "Validation check passed: bad requests rejected.\n";
    }

    // 4. Concurrency: 8 threads x 50 attempts, zero refill, capacity 10.
    //    Exactly 10 requests may succeed in total.
    {
        TokenBucketRateLimiter limiter(0.0 + 1e-9, 10.0);  // ~no refill
        std::atomic<int> granted{0};
        std::vector<std::thread> workers;
        for (int t = 0; t < 8; ++t) {
            workers.emplace_back([&] {
                for (int i = 0; i < 50; ++i) {
                    if (limiter.try_acquire()) {
                        ++granted;
                    }
                }
            });
        }
        for (auto& w : workers) {
            w.join();
        }
        assert(granted == 10);
        std::cout << "Concurrency check passed: exactly 10 of 400 "
                     "requests granted across 8 threads.\n";
    }

    // 5. Sustained rate: drain the bucket, then 20 tokens/sec over
    //    ~1 s allows ~20 more requests.
    {
        TokenBucketRateLimiter limiter(20.0, 20.0);
        for (int i = 0; i < 20; ++i) {
            assert(limiter.try_acquire());
        }
        assert(!limiter.try_acquire());
        int granted = 0;
        const auto start = std::chrono::steady_clock::now();
        while (std::chrono::steady_clock::now() - start < 1s) {
            if (limiter.try_acquire()) {
                ++granted;
            } else {
                std::this_thread::sleep_for(5ms);
            }
        }
        assert(granted >= 18 && granted <= 22);
        std::cout << "Sustained-rate check passed: " << granted
                  << " requests in 1 s at 20 tokens/sec.\n";
    }

    std::cout << "All rate limiter checks passed.\n";
    return 0;
}
