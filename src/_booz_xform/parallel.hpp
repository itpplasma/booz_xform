#ifndef BOOZ_XFORM_PARALLEL_HPP
#define BOOZ_XFORM_PARALLEL_HPP

/** Parallel loop over independent work items, built on std::thread.
 *
 *  booz_xform used to parallelize over magnetic surfaces with OpenMP. Every
 *  binary wheel then had to carry its own OpenMP runtime, and two copies of
 *  libomp cannot be initialized in one process (LLVM aborts with "OMP: Error
 *  #15"). Importing booz_xform next to another package that vendors libomp,
 *  such as a second build of booz_xform, therefore crashed on the first call.
 *  This header needs only the C++ standard library, so no OpenMP runtime is
 *  linked or loaded.
 */

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <exception>
#include <mutex>
#include <thread>
#include <vector>

namespace booz_xform {

/** Number of worker threads: OMP_NUM_THREADS if it is set to a positive
 *  integer (the first entry of a comma-separated list), otherwise the number
 *  of hardware threads. Always at least 1.
 */
inline int max_threads() {
  const char* env = std::getenv("OMP_NUM_THREADS");
  if (env != nullptr) {
    char* end = nullptr;
    long n = std::strtol(env, &end, 10);
    if (end != env && n > 0) return static_cast<int>(std::min<long>(n, 4096));
  }
  return std::max(1u, std::thread::hardware_concurrency());
}

/** Index (0-based) of the worker running the current loop body; 0 outside of
 *  parallel_for.
 */
inline int& current_thread() {
  static thread_local int id = 0;
  return id;
}

/** Mutex that serializes console output from concurrent loop bodies. */
inline std::mutex& output_mutex() {
  static std::mutex m;
  return m;
}

/** Call body(i) for i = 0 .. n-1, each exactly once, on up to max_threads()
 *  threads. Items are handed out dynamically, so the result of a body that
 *  only touches its own item does not depend on the thread count. The first
 *  exception thrown by a body is rethrown in the calling thread after all
 *  workers have stopped.
 */
template <class Body>
void parallel_for(int n, Body body) {
  const int nthreads = std::min(max_threads(), n);
  if (nthreads <= 1) {
    for (int i = 0; i < n; i++) body(i);
    return;
  }
  std::atomic<int> next(0);
  std::exception_ptr error;
  std::mutex error_mutex;
  auto worker = [&](int id) {
    current_thread() = id;
    for (;;) {
      int i = next.fetch_add(1);
      if (i >= n) break;
      try {
        body(i);
      } catch (...) {
        std::lock_guard<std::mutex> lock(error_mutex);
        if (!error) error = std::current_exception();
        next.store(n);
        break;
      }
    }
    current_thread() = 0;
  };
  std::vector<std::thread> pool;
  for (int id = 1; id < nthreads; id++) pool.emplace_back(worker, id);
  worker(0);
  for (auto& t : pool) t.join();
  if (error) std::rethrow_exception(error);
}

}  // namespace booz_xform

#endif
