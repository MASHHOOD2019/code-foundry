// Author: Mashhood Ali
//
// MemoryPool<T> - a fixed-size block allocator.
//
// Why it exists: calling new/delete (or malloc/free) for thousands of
// short-lived objects of the same type is slow and fragments the heap.
// A pool pre-allocates large chunks, carves them into equal-size blocks
// and hands them out from an intrusive free list, so allocate/deallocate
// are O(1) pointer operations with no system call on the hot path.
//
// Design:
//   * Chunks of BlocksPerChunk blocks are allocated with operator new[].
//     Each block is max(sizeof(T), sizeof(void*)) bytes so a free block
//     can hold the "next free" pointer, and is aligned to alignof(T).
//   * allocate() pops the head of the free list, growing a new chunk
//     when the list is empty. deallocate() pushes the block back.
//   * create()/destroy() wrap placement-new / explicit destructor calls
//     so the pool owns both memory and lifetime, like std::allocator.
//   * The pool is NOT thread-safe by design (no lock on the hot path);
//     give each thread its own pool, or guard it with a mutex.
//
// Complexity: allocate/deallocate O(1) time, O(1) extra memory per
// block (the pointer is stored inside the free block itself).
// Total memory is O(number of live blocks + one chunk of slack).

#ifndef MEMORY_POOL_HPP
#define MEMORY_POOL_HPP

#include <cstddef>
#include <new>
#include <utility>
#include <vector>

template <typename T, std::size_t BlocksPerChunk = 1024>
class MemoryPool {
public:
    MemoryPool() = default;

    MemoryPool(const MemoryPool&) = delete;
    MemoryPool& operator=(const MemoryPool&) = delete;

    ~MemoryPool() {
        // Live objects must have been destroyed by the caller via
        // destroy() before the pool dies; here we only release chunks.
        for (void* chunk : chunks_) {
            ::operator delete[](chunk, std::align_val_t(kAlignment));
        }
    }

    // Raw block, uninitialized. Pair with placement-new, or use create().
    T* allocate() {
        if (free_list_ == nullptr) {
            grow();
        }
        Block* block = free_list_;
        free_list_ = block->next;
        ++live_blocks_;
        return reinterpret_cast<T*>(block);
    }

    // Returns a block to the pool. The object must already be destroyed.
    void deallocate(T* ptr) noexcept {
        if (ptr == nullptr) {
            return;
        }
        Block* block = reinterpret_cast<Block*>(ptr);
        block->next = free_list_;
        free_list_ = block;
        --live_blocks_;
    }

    // Constructs a T in a pooled block and returns it.
    template <typename... Args>
    T* create(Args&&... args) {
        T* ptr = allocate();
        try {
            new (ptr) T(std::forward<Args>(args)...);
        } catch (...) {
            deallocate(ptr);
            throw;
        }
        return ptr;
    }

    // Destroys the object and returns its block to the pool.
    void destroy(T* ptr) noexcept {
        if (ptr == nullptr) {
            return;
        }
        ptr->~T();
        deallocate(ptr);
    }

    std::size_t live_blocks() const noexcept { return live_blocks_; }
    std::size_t total_blocks() const noexcept {
        return chunks_.size() * BlocksPerChunk;
    }
    std::size_t free_blocks() const noexcept {
        return total_blocks() - live_blocks_;
    }
    std::size_t chunk_count() const noexcept { return chunks_.size(); }

private:
    struct Block {
        Block* next;
    };

    // A block must fit both a T and the free-list pointer, and every
    // block start must satisfy alignof(T) so placement-new is legal.
    // Round the size up to a multiple of the alignment so consecutive
    // blocks inside a chunk stay aligned.
    static constexpr std::size_t kAlignment =
        alignof(T) > alignof(Block) ? alignof(T) : alignof(Block);
    static constexpr std::size_t kRawSize =
        sizeof(T) > sizeof(Block) ? sizeof(T) : sizeof(Block);
    static constexpr std::size_t kBlockSize =
        (kRawSize + kAlignment - 1) / kAlignment * kAlignment;

    void grow() {
        // operator new[] with an alignment guarantee: allocate raw bytes
        // aligned to kAlignment. std::aligned_alloc needs a size that is
        // a multiple of the alignment, which kBlockSize * BlocksPerChunk
        // satisfies by the static_assert above.
        const std::size_t bytes = kBlockSize * BlocksPerChunk;
        void* raw = ::operator new[](bytes, std::align_val_t(kAlignment));
        chunks_.push_back(raw);

        // Link the new blocks into the free list (in reverse so the
        // first block handed out is the lowest address).
        char* base = static_cast<char*>(raw);
        for (std::size_t i = BlocksPerChunk; i-- > 0;) {
            Block* block = reinterpret_cast<Block*>(base + i * kBlockSize);
            block->next = free_list_;
            free_list_ = block;
        }
    }

    Block* free_list_ = nullptr;
    std::vector<void*> chunks_;
    std::size_t live_blocks_ = 0;
};

#endif  // MEMORY_POOL_HPP
