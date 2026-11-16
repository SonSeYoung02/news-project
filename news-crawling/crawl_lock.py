import errno
import logging
import os
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

try:
    import fcntl  # type: ignore[attr-defined]
except ImportError:
    fcntl = None

try:
    import msvcrt  # type: ignore[attr-defined]
except ImportError:
    msvcrt = None


def get_crawl_lock_path() -> Path:
    """활성 DB 경로 또는 CRAWL_LOCK_PATH 환경 변수에서 공유 락 파일 경로를 결정한다."""
    explicit = os.environ.get("CRAWL_LOCK_PATH", "").strip()
    if explicit:
        return Path(explicit)

    from config import DB_PATH

    db_path = Path(os.environ.get("DB_PATH", str(DB_PATH)))
    return Path(f"{db_path}.crawl.lock")


class SharedCrawlLock:
    """수집·번역 파이프라인과 호스트 배포 스크립트가 공유하는 OS 파일 락(inode 유지)."""

    def __init__(self, lock_path: Optional[Union[str, Path]] = None):
        self.lock_path = Path(lock_path) if lock_path is not None else get_crawl_lock_path()
        self._fd: Optional[int] = None

    def _open_fd(self) -> int:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        flags = os.O_CREAT | os.O_RDWR | cloexec
        try:
            fd = os.open(self.lock_path, flags, 0o666)
        except PermissionError:
            # 호스트에서 다른 UID로 미리 만든 락 파일이면 POSIX flock은 O_RDONLY로도 잠글 수 있다.
            if fcntl is None or not self.lock_path.exists():
                raise
            fd = os.open(self.lock_path, os.O_RDONLY | cloexec)
        os.set_inheritable(fd, False)
        return fd

    def acquire(self) -> bool:
        if self._fd is not None:
            return False

        fd = self._open_fd()
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    return False
                except OSError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                        os.close(fd)
                        return False
                    raise
            elif msvcrt is not None:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    if exc.errno in (errno.EACCES, errno.EDEADLK):
                        os.close(fd)
                        return False
                    raise
            else:
                os.close(fd)
                raise RuntimeError("지원되는 OS 파일 잠금 API(fcntl/msvcrt)가 없습니다.")
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        self._fd = fd
        return True

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError as exc:
                    logger.warning("flock 해제 실패(%s): %s", self.lock_path, exc)
            elif msvcrt is not None:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    logger.warning("msvcrt 락 해제 실패(%s): %s", self.lock_path, exc)
        finally:
            # 잠금 파일 inode는 유지해야 하므로 절대 삭제하지 않는다.
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> "SharedCrawlLock":
        if not self.acquire():
            raise BlockingIOError(f"공유 락을 획득할 수 없습니다: {self.lock_path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
