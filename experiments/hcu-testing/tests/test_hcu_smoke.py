"""Small real-device validation, no models/network required."""
import pytest
import torch


@pytest.mark.parametrize('dtype', [torch.float32, torch.float16, torch.bfloat16])
@pytest.mark.parametrize('shape', [(4, 8), (7, 13)])
def test_hcu_matmul_against_cpu(dtype, shape):
    generator = torch.Generator().manual_seed(42)
    a = torch.randn(shape, generator=generator).to(dtype)
    b = torch.randn((shape[1], 5), generator=generator).to(dtype)
    expected = a.float() @ b.float()
    actual = (a.to('cuda') @ b.to('cuda')).float().cpu()
    tolerance = {torch.float32: 1e-4, torch.float16: 1e-2, torch.bfloat16: 8e-2}[dtype]
    torch.testing.assert_close(actual, expected, atol=tolerance, rtol=tolerance)


def test_non_contiguous_add():
    a = torch.arange(24, dtype=torch.float32).reshape(4, 6).to('cuda').t()
    assert not a.is_contiguous()
    torch.testing.assert_close((a + 2).cpu(), torch.arange(24).reshape(4, 6).t().float() + 2)


def test_empty_tensor():
    a = torch.empty((0, 8), device='cuda')
    assert (a + 1).cpu().shape == (0, 8)


def test_invalid_matmul_shape():
    with pytest.raises(RuntimeError):
        torch.ones((2, 3), device='cuda') @ torch.ones((4, 2), device='cuda')


def test_numerical_assertion_detects_wrong_result():
    correct = (torch.ones(4, device='cuda') + 1).cpu()
    with pytest.raises(AssertionError):
        torch.testing.assert_close(correct, torch.full((4,), 3.0))
