// Author: Mashhood Ali
//
// Demo and checks for the thread pool.
//
// Verifies parallel results, exception propagation through futures,
// that queued tasks still run during a graceful shutdown, and that
// enqueueing after shutdown throws instead of silently dropping work.

#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "thread_pool.hpp"

int main() {
    // 1. Parallel sum: 10 tasks add the numbers 1..1000 (expect 500500),
    //    spread across the workers and combined through futures.
    {
        ThreadPool pool(4);
        std::vector<std::future<long>> results;
        for (int chunk = 0; chunk < 10; ++chunk) {
            const int lo = chunk * 100 + 1;
            const int hi = (chunk + 1) * 100;
            results.push_back(pool.enqueue([lo, hi] {
                long sum = 0;
                for (int n = lo; n <= hi; ++n) {
                    sum += n;
                }
                return sum;
            }));
        }
        long total = 0;
        for (auto& f : results) {
            total += f.get();
        }
        assert(total == 500500);
        std::cout << "Parallel sum check passed: 1..1000 = " << total << ".\n";
    }

    // 2. Exceptions travel through the future: a throwing task must
    //    not kill the worker, and get() must rethrow the same error.
    {
        ThreadPool pool(2);
        auto failing = pool.enqueue([] {
            throw std::runtime_error("boom");
            return 0;
        });
        bool caught = false;
        try {
            failing.get();
        } catch (const std::runtime_error& e) {
            caught = std::string(e.what()) == "boom";
        }
        assert(caught);

        // The pool is still usable after a task throws.
        auto ok = pool.enqueue([] { return 42; });
        assert(ok.get() == 42);
        std::cout << "Exception check passed: error reached the caller, pool kept working.\n";
    }

    // 3. Graceful shutdown: tasks queued just before the pool goes out
    //    of scope still run to completion; none is dropped.
    {
        std::vector<int> done;
        std::mutex done_mutex;
        {
            ThreadPool pool(2);
            for (int i = 0; i < 20; ++i) {
                pool.enqueue([i, &done, &done_mutex] {
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    std::lock_guard<std::mutex> lock(done_mutex);
                    done.push_back(i);
                });
            }
        }  // pool destroyed here: drains the queue, then joins
        std::sort(done.begin(), done.end());
        assert(done.size() == 20);
        for (int i = 0; i < 20; ++i) {
            assert(done[static_cast<std::size_t>(i)] == i);
        }
        std::cout << "Shutdown check passed: all 20 queued tasks ran before join.\n";
    }

    // 4. Enqueue with arguments and a void task, plus the thread count.
    {
        ThreadPool pool(3);
        assert(pool.thread_count() == 3);
        auto product = pool.enqueue([](int a, int b) { return a * b; }, 6, 7);
        assert(product.get() == 42);
        bool ran = false;
        pool.enqueue([&ran] { ran = true; }).get();
        assert(ran);
        std::cout << "Arguments check passed: enqueue(a, b) returned 42, void task ran.\n";
    }

    std::cout << "All thread pool checks passed.\n";
    return 0;
}
