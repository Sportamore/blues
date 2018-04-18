$TTL	604800
@	IN	SOA	{{ zone }}. root.{{ zone }}. (
			{{ serial }}		; Serial
			 604800		; Refresh
			  86400		; Retry
			2419200		; Expire
			 604800 )	; Negative Cache TTL