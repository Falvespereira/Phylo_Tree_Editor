<script>
	//variable Init
	let count = 0;
	//function to be called on click
	function incrementCount() {
		//incremtent
		count++
	}
</script>
<!-- the function will be called on click -->
<button on:click={incrementCount}>
	Clicked  {count} {count === 1 ? 'time': 'times'}
</button>