// Author: Mashhood Ali
//
// Thread-safe token bucket rate limiter.
//
// A bucket holds up to `capacity` tokens and refills continuously at
// `rate_per_second` tokens per second. Each request spends one token
// (or `tokens` tokens); when the bucket is empty the request is
// rejected immediately instead of queueing, so a burst of traffic can
// never overwhelm the downstream service.
//
// Complexity: O(1) time and O(1) memory per acquire. All state is
// guarded by a single mutex, so the limiter is safe to share across
// threads with no external synchronisation.
//
// Typical uses: throttling outbound API calls, protecting a database
// from retry storms, or capping requests per client in a server.

#ifndef RATE_LIMITER_HPP
#define RATE_LIMITER_HPP

#include <algorithm>
#include <chrono>
#include <mutex>
#include <stdexcept>

class TokenBucketRateLimiter {
public:
    // rate_per_second: sustained refill rate (may be fractional).
    // capacity:        maximum burst size; also the starting token count.
    // Both must be positive; a zero rate would never refill.
    TokenBucketRateLimiter(double rate_per_second, double capacity)
        : rate_per_second_(rate_per_second),
          capacity_(capacity),
          tokens_(capacity),
          last_refill_(std::chrono::steady_clock::now()) {
        if (rate_per_second_ <= 0.0 || capacity_ <= 0.0) {
            throw std::invalid_argument(
                "rate_per_second and capacity must be positive");
        }
    }

    // Non-copyable: the mutex and the refill clock make copies unsafe.
    TokenBucketRateLimiter(const TokenBucketRateLimiter&) = delete;
    TokenBucketRateLimiter& operator=(const TokenBucketRateLimiter&) = delete;

    // Try to spend `tokens` tokens. Returns true when the request is
    // allowed, false when the bucket is too empty (no tokens are spent).
    bool try_acquire(double tokens = 1.0) {
        if (tokens <= 0.0 || tokens > capacity_) {
            return false;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        refill_locked();
        if (tokens_ < tokens) {
            return false;
        }
        tokens_ -= tokens;
        return true;
    }

    // Tokens currently available (after refilling up to now).
    // Useful for monitoring; the value can change the moment it is read.
    double available() {
        std::lock_guard<std::mutex> lock(mutex_);
        refill_locked();
        return tokens_;
    }

    double rate_per_second() const { return rate_per_second_; }
    double capacity() const { return capacity_; }

private:
    // Adds the tokens earned since the last refill, capped at capacity.
    // Must be called with mutex_ held.
    void refill_locked() {
        const auto now = std::chrono::steady_clock::now();
        const double elapsed =
            std::chrono::duration<double>(now - last_refill_).count();
        if (elapsed > 0.0) {
            tokens_ = std::min(capacity_,
                               tokens_ + elapsed * rate_per_second_);
            last_refill_ = now;
        }
    }

    const double rate_per_second_;
    const double capacity_;
    double tokens_;
    std::chrono::steady_clock::time_point last_refill_;
    std::mutex mutex_;
};

#endif  // RATE_LIMITER_HPP
